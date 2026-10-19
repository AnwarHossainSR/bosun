"""Tests for plugins/bosun/scripts/taskboard.py (run: python3 -m unittest discover -s tests)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "bosun" / "scripts" / "taskboard.py"
EXAMPLE_40 = ROOT / "examples" / "taskflow-40" / "tasks.json"

spec = importlib.util.spec_from_file_location("taskboard", SCRIPT)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)


def task(tid, deps=(), files=(), **extra):
    data = {"id": tid, "title": f"task {tid}", "deps": list(deps), "files": list(files),
            "acceptance": ["it works"]}
    data.update(extra)
    return data


def board(*tasks, **meta):
    return {"name": "t", "version": 1, "meta": dict(meta), "tasks": list(tasks)}


class OverlapTests(unittest.TestCase):
    def test_exact_and_disjoint_files(self):
        self.assertTrue(tb.paths_overlap("src/a.ts", "./src/a.ts"))
        self.assertFalse(tb.paths_overlap("src/a.ts", "src/b.ts"))

    def test_directory_ownership(self):
        self.assertTrue(tb.paths_overlap("src/auth/", "src/auth/login.ts"))
        self.assertTrue(tb.paths_overlap("src/auth/**", "src/auth/deep/x.ts"))
        self.assertTrue(tb.paths_overlap("src/", "src/auth/"))
        self.assertFalse(tb.paths_overlap("src/auth/", "src/authz/x.ts"))

    def test_globs_are_conservative(self):
        self.assertTrue(tb.paths_overlap("src/*.ts", "src/a.ts"))
        self.assertTrue(tb.paths_overlap("**/*.test.ts", "anything/at/all.py"))
        self.assertFalse(tb.paths_overlap("docs/*.md", "src/a.ts"))

    def test_windows_separators(self):
        self.assertTrue(tb.paths_overlap("src\\auth\\", "src/auth/x.ts"))


class ValidateTests(unittest.TestCase):
    def test_valid_board(self):
        errors, _ = tb.validate_board(board(task("T1"), task("T2", ["T1"])))
        self.assertEqual(errors, [])

    def test_cycle_unknown_dup_self(self):
        errors, _ = tb.validate_board(board(task("A", ["B"]), task("B", ["A"])))
        self.assertTrue(any("cycle" in e for e in errors), errors)
        errors, _ = tb.validate_board(board(task("A", ["Z"])))
        self.assertTrue(any("unknown dependency Z" in e for e in errors), errors)
        errors, _ = tb.validate_board(board(task("A"), task("A")))
        self.assertTrue(any("duplicate" in e for e in errors), errors)
        errors, _ = tb.validate_board(board(task("A", ["A"])))
        self.assertTrue(any("itself" in e for e in errors), errors)

    def test_bad_types_and_status(self):
        errors, _ = tb.validate_board(board({"id": "A", "title": "x", "deps": "B"}))
        self.assertTrue(any("'deps' must be a list" in e for e in errors), errors)
        errors, _ = tb.validate_board(board(task("A", status="doing")))
        self.assertTrue(any("invalid status" in e for e in errors), errors)
        errors, _ = tb.validate_board({"tasks": "nope"})
        self.assertTrue(errors)

    def test_overlap_warning_only_for_unordered_tasks(self):
        _, warnings = tb.validate_board(board(task("A", files=["x.ts"]), task("B", files=["x.ts"])))
        self.assertTrue(any("both own" in w for w in warnings), warnings)
        _, warnings = tb.validate_board(board(task("A", files=["x.ts"]), task("B", ["A"], files=["x.ts"])))
        self.assertFalse(any("both own" in w for w in warnings), warnings)

    def test_report_tasks_need_no_files(self):
        _, warnings = tb.validate_board(board({"id": "R", "title": "recon", "agent": "scout"}))
        self.assertFalse(any("no files" in w for w in warnings), warnings)


class NextTests(unittest.TestCase):
    def test_respects_deps_and_slots(self):
        b = board(task("A", files=["a"]), task("B", files=["b"]), task("C", ["A"], files=["c"]))
        result = tb.plan_next(b, parallel=1)
        self.assertEqual(len(result["start"]), 1)
        result = tb.plan_next(b, parallel=4)
        self.assertEqual(sorted(t["id"] for t in result["start"]), ["A", "B"])

    def test_inflight_consumes_slots_and_locks_files(self):
        b = board(task("A", files=["src/x.ts"], status="in_progress"),
                  task("B", files=["src/x.ts"]), task("C", files=["src/y.ts"]))
        result = tb.plan_next(b, parallel=3)
        self.assertEqual([t["id"] for t in result["start"]], ["C"])
        self.assertEqual(result["deferred"], [{"id": "B", "waits_for": "A", "path": "src/x.ts"}])
        self.assertEqual(result["slots"], 2)

    def test_batch_members_are_file_disjoint(self):
        b = board(task("A", files=["src/"]), task("B", files=["src/b.ts"]), task("C", files=["lib/c.ts"]))
        ids = [t["id"] for t in tb.plan_next(b, parallel=5)["start"]]
        self.assertIn("C", ids)
        self.assertFalse({"A", "B"} <= set(ids))

    def test_critical_path_first(self):
        b = board(task("LONE", files=["z"]), task("ROOT", files=["r"]),
                  task("MID", ["ROOT"], files=["m"]), task("LEAF", ["MID"], files=["l"]))
        first = tb.plan_next(b, parallel=1)["start"][0]["id"]
        self.assertEqual(first, "ROOT")

    def test_strict_files_runs_undeclared_alone(self):
        b = board(task("A"), task("B", files=["b"]))
        self.assertEqual(len(tb.plan_next(b, parallel=4)["start"]), 2)
        self.assertEqual(len(tb.plan_next(b, parallel=4, strict_files=True)["start"]), 1)

    def test_report_tasks_do_not_lock_files(self):
        b = board(task("R", files=["src/"], agent="scout"), task("A", files=["src/a.ts"]))
        self.assertEqual(len(tb.plan_next(b, parallel=4)["start"]), 2)

    def test_stuck_and_complete(self):
        b = board(task("A", status="failed"), task("B", ["A"]))
        result = tb.plan_next(b, parallel=4)
        self.assertTrue(result["stuck"])
        self.assertFalse(result["complete"])
        b = board(task("A", status="done"), task("B", ["A"], status="skipped"))
        self.assertTrue(tb.plan_next(b, parallel=4)["complete"])


class WavesTests(unittest.TestCase):
    def test_waves_and_unschedulable(self):
        b = board(task("A", files=["a"]), task("B", files=["b"]), task("C", ["A", "B"], files=["c"]),
                  task("D", status="blocked"), task("E", ["D"], files=["e"]))
        waves, unschedulable, critical = tb.simulate_waves(b, parallel=4)
        self.assertEqual(waves, [["A", "B"], ["C"]])
        self.assertEqual(unschedulable, ["E"])
        self.assertEqual(critical, 4)  # A (M=2) -> C (M=2); E is unschedulable but still counted

    def test_critical_path_shrinks_as_work_finishes(self):
        b = board(task("A", size="L"), task("B", ["A"], size="S"))
        self.assertEqual(tb.simulate_waves(b, parallel=2)[2], 4)
        b["tasks"][0]["status"] = "done"
        self.assertEqual(tb.simulate_waves(b, parallel=2)[2], 1)

    def test_parallel_cap(self):
        b = board(*[task(f"T{i}", files=[f"f{i}"]) for i in range(10)])
        waves, _, _ = tb.simulate_waves(b, parallel=3)
        self.assertEqual([len(w) for w in waves], [3, 3, 3, 1])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()
        self.board = self.root / ".bosun" / "plans" / "demo" / "tasks.json"
        self.board.parent.mkdir(parents=True)
        self.board.write_text(json.dumps(tb.EXAMPLE_BOARD))

    def tearDown(self):
        self.tmp.cleanup()

    def run_tb(self, *args, check=True):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=60)
        if check and proc.returncode != 0:
            self.fail(f"taskboard {args} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return proc

    def load(self):
        return json.loads(self.board.read_text())

    def test_validate_and_resolve_by_slug(self):
        out = self.run_tb("validate", "demo").stdout
        self.assertIn("OK: 6 tasks", out)
        self.assertEqual(self.run_tb("latest").stdout.strip(), str(self.board.resolve()))

    def test_set_lifecycle(self):
        self.run_tb("set", "demo", "T01", "--status", "in_progress", "--assignee", "bosun:implementer")
        t = self.load()["tasks"][0]
        self.assertEqual((t["status"], t["attempts"], t["assignee"]), ("in_progress", 1, "bosun:implementer"))
        self.assertIn("started_at", t)
        self.run_tb("set", "demo", "T01", "--status", "done", "--commit", "abc123", "--summary", "scaffolded")
        t = self.load()["tasks"][0]
        self.assertEqual((t["status"], t["commit"], t["summary"]), ("done", "abc123", "scaffolded"))
        self.assertEqual([h["to"] for h in t["history"]], ["in_progress", "done"])
        nxt = json.loads(self.run_tb("next", "demo", "--json").stdout)
        self.assertEqual([s["id"] for s in nxt["start"]], ["T02"])

    def test_unknown_id_fails(self):
        proc = self.run_tb("set", "demo", "T99", "--status", "done", check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("unknown task id", proc.stderr)

    def test_concurrent_writes_do_not_lose_updates(self):
        def note(i):
            return subprocess.run([sys.executable, str(SCRIPT), "set", str(self.board), "T03", "--note", f"n{i}"],
                                  cwd=self.root, capture_output=True, text=True, timeout=60).returncode
        with ThreadPoolExecutor(max_workers=12) as pool:
            codes = list(pool.map(note, range(24)))
        self.assertEqual(codes, [0] * 24)
        notes = self.load()["tasks"][2]["notes"]
        self.assertEqual(sorted(n.split()[-1] for n in notes), sorted(f"n{i}" for i in range(24)))
        self.assertFalse(Path(str(self.board) + ".lock").exists())

    def test_add_rejects_cycles_and_unknown_deps(self):
        self.run_tb("add", "demo", "--id", "T07", "--title", "Fix", "--deps", "T05", "--files", "src/x.ts",
                    "--acceptance", "tests pass")
        self.assertEqual(self.load()["tasks"][-1]["deps"], ["T05"])
        proc = self.run_tb("add", "demo", "--id", "T08", "--title", "Bad", "--deps", "NOPE", check=False)
        self.assertEqual(proc.returncode, 1)
        proc = self.run_tb("add", "demo", "--id", "T01", "--title", "Dup", check=False)
        self.assertEqual(proc.returncode, 1)

    def test_brief_contains_contract(self):
        self.run_tb("set", "demo", "T01", "--status", "done", "--summary", "scaffold ok", "--commit", "c0ffee")
        self.run_tb("set", "demo", "T02", "--status", "done", "--summary", "schema ok")
        self.run_tb("set", "demo", "T04", "--status", "in_progress")
        brief = self.run_tb("brief", "demo", "T03").stdout
        for needle in ("# Task T03", "SECURITY-SENSITIVE", "## Acceptance criteria", "src/auth/",
                       "result: schema ok", "do not touch their files", "src/todos/"):
            self.assertIn(needle, brief)

    def test_status_waves_graph_meta_activity(self):
        status = json.loads(self.run_tb("status", "demo", "--json").stdout)
        self.assertEqual(status["total"], 6)
        self.assertEqual(status["ready"], ["T01"])
        waves = json.loads(self.run_tb("waves", "demo", "--json", "--parallel", "3").stdout)
        self.assertEqual(waves["waves"][0], ["T01"])
        self.assertIn("flowchart TD", self.run_tb("graph", "demo").stdout)
        meta = json.loads(self.run_tb("meta", "demo", "--set", "work_branch=bosun/demo", "--set", "max_parallel=2").stdout)
        self.assertEqual((meta["work_branch"], meta["max_parallel"]), ("bosun/demo", 2))
        log = self.root / ".bosun" / "activity.jsonl"
        log.write_text(json.dumps({"ts": "2026-01-01T00:00:00Z", "event": "start", "agent_type": "bosun:implementer",
                                   "agent_id": "a1"}) + "\nnot json\n")
        activity = json.loads(self.run_tb("activity", "demo", "--json").stdout)
        self.assertEqual(len(activity["running"]), 1)
        self.assertIn("planning rules", self.run_tb("schema").stdout.lower())
        json.loads(self.run_tb("example").stdout)

    def test_init(self):
        path = Path(self.run_tb("init", "fresh-plan", "--title", "Fresh").stdout.strip())
        self.assertTrue(path.is_file())
        self.assertEqual(self.run_tb("init", "fresh-plan", check=False).returncode, 1)
        self.assertEqual(self.run_tb("init", "Bad Slug", check=False).returncode, 1)


@unittest.skipUnless(EXAMPLE_40.is_file(), "example board not present")
class ExampleBoardTests(unittest.TestCase):
    def test_example_40_is_valid_and_parallel(self):
        b = json.loads(EXAMPLE_40.read_text())
        errors, warnings = tb.validate_board(b)
        self.assertEqual(errors, [])
        self.assertEqual(len(b["tasks"]), 40)
        waves, unschedulable, _ = tb.simulate_waves(b, parallel=5)
        self.assertEqual(unschedulable, [])
        self.assertEqual(sum(len(w) for w in waves), 40)
        self.assertGreaterEqual(max(len(w) for w in waves), 4)


class VersionTests(unittest.TestCase):
    def test_cli_version_matches_the_plugin_manifest(self):
        manifest = json.loads((ROOT / "plugins" / "bosun" / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(tb.VERSION, manifest["version"])


if __name__ == "__main__":
    unittest.main()
