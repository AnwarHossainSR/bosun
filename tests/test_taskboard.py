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

    def test_start_entries_carry_the_gate_inputs(self):
        # The build picks review lenses from these instead of reading every brief.
        b = board(task("A", files=["a"], risk="high", spec_refs=["todo-items#Items are private"]), task("B", files=["b"]))
        start = {t["id"]: t for t in tb.plan_next(b, parallel=4)["start"]}
        self.assertEqual((start["A"]["risk"], start["A"]["spec_refs"]), ("high", ["todo-items#Items are private"]))
        self.assertEqual((start["B"]["risk"], start["B"]["spec_refs"]), ("unknown", []))

    def test_only_keeps_unlisted_tasks_out_of_the_slots(self):
        # ROOT ranks first on the critical path; with --only LONE it must not take the only slot.
        b = board(task("LONE", files=["z"]), task("ROOT", files=["r"]), task("MID", ["ROOT"], files=["m"]))
        self.assertEqual([t["id"] for t in tb.plan_next(b, parallel=1)["start"]], ["ROOT"])
        result = tb.plan_next(b, parallel=1, only=["LONE"])
        self.assertEqual([t["id"] for t in result["start"]], ["LONE"])
        self.assertFalse(result["complete"])
        b = board(task("LONE", files=["z"], status="done"), task("ROOT", files=["r"]))
        self.assertTrue(tb.plan_next(b, parallel=1, only=["LONE"])["complete"])
        stuck = tb.plan_next(board(task("ROOT", files=["r"]), task("MID", ["ROOT"], files=["m"])), 1, only=["MID"])
        self.assertTrue(stuck["stuck"])  # its dependency isn't listed, so it can never start

    def test_only_rejects_unknown_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            path.write_text(json.dumps(board(task("A", files=["a"]))))
            proc = subprocess.run([sys.executable, str(SCRIPT), "next", str(path), "--only", "A,ZZ", "--json"],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ZZ", proc.stderr)

    def test_json_output_is_one_compact_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.json"
            path.write_text(json.dumps(board(task("A", files=["a"]))))
            proc = subprocess.run([sys.executable, str(SCRIPT), "next", str(path), "--json"],
                                  capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count("\n"), 1)
        self.assertNotIn(", ", proc.stdout)
        self.assertEqual(json.loads(proc.stdout)["start"][0]["id"], "A")

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


class RouteTests(unittest.TestCase):
    def test_small_writer_board_runs_solo_in_id_order(self):
        # Id order (tasks.md order) wherever the deps allow it: 1.2 waits for 2.1, and 1.10 sorts after 1.9.
        b = board(task("1.1"), task("1.2", ["2.1"]), task("2.1", ["1.1"]), task("1.9"), task("1.10"),
                  task("3.1", agent="test-engineer"), task("3.2", agent="docs-writer"))
        result = tb.plan_route(b)
        self.assertEqual((result["route"], result["solo_ok"], result["large"]), ("solo", True, False))
        self.assertEqual(result["order"], ["1.1", "1.9", "1.10", "2.1", "1.2", "3.1", "3.2"])
        self.assertEqual((result["tasks"], result["size_units"], result["reasons"]), (7, 14, []))

    def test_finished_tasks_drop_out(self):
        b = board(task("A", status="done"), task("B", ["A"]), task("C", status="skipped"), task("D", ["C"]))
        result = tb.plan_route(b)
        self.assertEqual((result["route"], result["order"], result["tasks"]), ("solo", ["B", "D"], 2))
        self.assertEqual(tb.plan_route(board(task("A", status="done")))["route"], "none")

    def test_large_plans_keep_the_crew(self):
        many = tb.plan_route(board(*[task(f"T{i}", size="S") for i in range(tb.SOLO_MAX_TASKS + 1)]))
        self.assertEqual((many["route"], many["large"], many["solo_ok"]), ("crew", True, True))
        self.assertIn("over the solo limit", many["reasons"][0])
        heavy = tb.plan_route(board(*[task(f"T{i}", size="L") for i in range(6)]))  # 18 size-units
        self.assertEqual((heavy["route"], heavy["large"], heavy["size_units"]), ("crew", True, 18))
        at_limit = tb.plan_route(board(*[task(f"T{i}") for i in range(tb.SOLO_MAX_TASKS)]))  # 8 x M = 16
        self.assertEqual(at_limit["route"], "solo")

    def test_tasks_for_other_agents_need_the_crew(self):
        # Another plugin's implementer is not bosun's: the solo run would replace it with bosun:implementer.
        for extra in ({"agent": "scout"}, {"agent": "my-team-agent"}, {"kind": "report"}, {"agent": "acme:implementer"}):
            result = tb.plan_route(board(task("A"), task("B", ["A"], **extra)))
            self.assertEqual((result["route"], result["solo_ok"], result["large"]), ("crew", False, False), extra)
            self.assertIn("needs its own agent: B", result["reasons"][0])

    def test_bosun_writer_names_and_blank_agents_run_solo(self):
        b = board(task("A", agent="bosun:implementer"), task("B", agent="  "), task("C", agent="bosun:docs-writer"))
        self.assertEqual(tb.plan_route(b)["route"], "solo")

    def test_review_tasks_wait_for_their_gate_not_an_implementer(self):
        # A resume gates tasks in review first; they are built, so they stay out of the order but unblock dependents.
        b = board(task("A", status="done"), task("B", ["A"], status="review"), task("C", ["A"], status="in_progress"),
                  task("D", ["B", "C"]))
        result = tb.plan_route(b)
        self.assertEqual((result["order"], result["in_review"], result["tasks"]), (["C", "D"], ["B"], 2))
        self.assertEqual(tb.plan_route(b, only=["D"])["waiting"], ["D"])  # C is unlisted and unfinished
        b["tasks"].append(task("E", ["B"]))
        self.assertEqual(tb.plan_route(b, only=["E"])["route"], "solo")  # not stuck behind a task in review
        only_review = tb.plan_route(board(task("A", status="done"), task("B", ["A"], status="review")))
        self.assertEqual((only_review["route"], only_review["in_review"]), ("none", ["B"]))

    def test_waiting_stuck_and_only(self):
        b = board(task("A", status="blocked"), task("B", ["A"]), task("C"), task("D", ["C"]))
        result = tb.plan_route(b)
        self.assertEqual((result["route"], result["order"], result["waiting"]), ("solo", ["C", "D"], ["B"]))
        self.assertEqual(tb.plan_route(b, only=["B"])["route"], "stuck")
        self.assertEqual(tb.plan_route(b, only=["D"])["waiting"], ["D"])  # its unlisted dependency C isn't done
        self.assertEqual(tb.plan_route(b, only=["C", "D"])["order"], ["C", "D"])

    def test_security_sensitive_tasks_are_listed(self):
        b = board(task("A"), task("B", security_sensitive=True), task("C", ["B"], security_sensitive=True))
        self.assertEqual(tb.plan_route(b)["security_sensitive"], ["B", "C"])

    def test_example_boards(self):
        todo = ROOT / "examples" / "openspec-todo-api" / ".bosun" / "plans" / "add-todo-api" / "tasks.json"
        result = tb.plan_route(json.loads(todo.read_text()))
        self.assertEqual(result["route"], "solo")
        self.assertEqual(result["order"], ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1", "3.2", "4.1"])
        if EXAMPLE_40.is_file():
            self.assertEqual(tb.plan_route(json.loads(EXAMPLE_40.read_text()))["route"], "crew")


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

    def test_solo_briefs_have_no_other_writers(self):
        # In a solo run every in-flight task is the same implementer's, done in order.
        self.run_tb("set", "demo", "T01", "T02", "T03", "T04", "--status", "in_progress")
        self.run_tb("meta", "demo", "--set", "route=solo")
        brief = self.run_tb("brief", "demo", "T03").stdout
        self.assertNotIn("In flight right now", brief)
        self.assertIn("- T02 [earlier in this solo run]", brief)
        self.assertIn("Route: solo", self.run_tb("status", "demo").stdout)
        self.run_tb("meta", "demo", "--set", "route=crew")
        self.assertIn("do not touch their files", self.run_tb("brief", "demo", "T03").stdout)

    def test_solo_run_reads_as_one_run(self):
        self.run_tb("set", "demo", "T01", "T02", "T03", "--status", "in_progress")
        self.assertIn("in_progress but its deps", self.run_tb("validate", "demo").stdout)
        self.run_tb("meta", "demo", "--set", "route=solo")
        out = self.run_tb("validate", "demo").stdout
        self.assertNotIn("in_progress but its deps", out)  # a solo run marks its tasks in flight together
        self.assertIn("Remaining: 6 task(s) to build in one solo run, in order (", self.run_tb("status", "demo").stdout)
        self.run_tb("set", "demo", "T01", "--status", "review")  # built, waiting for its gate: not counted as left to build
        self.assertIn("Remaining: 5 task(s) to build in one solo run, in order, 1 in review", self.run_tb("status", "demo").stdout)

    def test_route_text_outcomes(self):
        self.run_tb("set", "demo", "T01", "--status", "blocked")
        out = self.run_tb("route", "demo").stdout
        self.assertIn("route: stuck", out)
        self.assertIn("waiting (behind blocked", out)
        self.run_tb("set", "demo", "T01", "T02", "T03", "T04", "T05", "T06", "--status", "done")
        self.assertIn("route: none", self.run_tb("route", "demo").stdout)
        board9 = self.root / ".bosun" / "plans" / "big" / "tasks.json"
        board9.parent.mkdir(parents=True)
        board9.write_text(json.dumps(board(*[task(f"T{i}", size="S") for i in range(9)])))
        out = self.run_tb("route", str(board9)).stdout
        self.assertIn("route: crew", out)
        self.assertIn("solo order: T0 T1", out)  # --solo still has an order to use

    def test_route_cli(self):
        result = json.loads(self.run_tb("route", "demo", "--json").stdout)
        self.assertEqual((result["route"], result["order"]), ("solo", ["T01", "T02", "T03", "T04", "T05", "T06"]))
        text = self.run_tb("route", "demo", "--only", "T01,T02").stdout
        self.assertIn("route: solo (2 tasks", text)
        self.assertIn("solo order: T01 T02", text)
        proc = self.run_tb("route", "demo", "--only", "T01,NOPE", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("NOPE", proc.stderr)

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
