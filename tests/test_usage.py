"""Tests for plugins/bosun/scripts/usage.py (run: python3 -m unittest discover -s tests)."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "bosun" / "scripts" / "usage.py"

spec = importlib.util.spec_from_file_location("usage", SCRIPT)
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


def reply(msg_id, ts, inp=0, write=0, read=0, out=0, model="claude-test", stop="end_turn"):
    return {"type": "assistant", "timestamp": ts, "uuid": f"u-{msg_id}-{out}",
            "message": {"id": msg_id, "model": model, "stop_reason": stop, "usage": {
                "input_tokens": inp, "cache_creation_input_tokens": write,
                "cache_read_input_tokens": read, "output_tokens": out}}}


def write_jsonl(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.config = self.base / "config"
        self.project = self.base / "work" / "my-app"
        self.project.mkdir(parents=True)
        self.folder = self.config / "projects" / usage.project_slug(str(self.project.resolve()))
        self.transcript = self.folder / "sess-1.jsonl"
        write_jsonl(self.transcript, [
            {"type": "user", "timestamp": "2026-10-23T09:00:00Z", "cwd": str(self.project)},
            # One response written as two lines (two content blocks): counted once, with the larger output.
            reply("m1", "2026-10-23T09:00:05Z", inp=10, write=1000, read=0, out=5, stop=None),
            reply("m1", "2026-10-23T09:00:05Z", inp=10, write=1000, read=0, out=40),
            reply("m2", "2026-10-23T10:00:05Z", inp=2, write=100, read=1000, out=60),
            {"type": "user", "timestamp": "2026-10-23T10:00:06Z", "message": {"content": "no usage here"}},
        ])
        agent = self.folder / "sess-1" / "subagents" / "agent-a1.jsonl"
        write_jsonl(agent, [reply("s1", "2026-10-23T10:00:10Z", inp=1, write=500, read=0, out=7)])
        agent.with_name("agent-a1.meta.json").write_text(json.dumps(
            {"agentType": "bosun:code-reviewer", "description": "Review correctness"}), encoding="utf-8")
        old = self.folder / "sess-1" / "subagents" / "agent-a0.jsonl"
        write_jsonl(old, [reply("s0", "2026-10-23T09:00:10Z", out=3, read=100)])
        self.env = dict(os.environ, CLAUDE_CONFIG_DIR=str(self.config))
        self.env.pop("CLAUDE_CODE_SESSION_ID", None)
        patcher = mock.patch.dict(os.environ, self.env, clear=True)  # in-process calls see only this fixture
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_usage(self, *args, cwd=None, env=None, check=True):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd or self.project, env=env or self.env,
                              capture_output=True, text=True, encoding="utf-8", timeout=60)
        if check and proc.returncode != 0:
            self.fail(f"usage.py {args} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return proc


class SlugTests(unittest.TestCase):
    def test_folder_names_follow_claude_code(self):
        self.assertEqual(usage.project_slug("/home/user/bosun"), "-home-user-bosun")
        self.assertEqual(usage.project_slug("D:\\Workspace\\teikna-project\\teikna"), "D--Workspace-teikna-project-teikna")
        long = "/home/" + "x" * 230 + "/é😀"
        # From Claude Code's own rule run in JavaScript: cut at 200 characters, then the base-36 string hash.
        self.assertEqual(usage.project_slug(long), "-home-" + "x" * 194 + "-yi6c9q")
        self.assertEqual(usage._java_hash("hello"), 99162322)


class UsageTests(Fixture):
    def test_agent_output_without_a_final_line_is_a_lower_bound(self):
        # A subagent's reply saved only at the start of its stream: input counts are final, output isn't.
        agent = self.folder / "sess-1" / "subagents" / "workflows" / "run-1" / "agent-w1.jsonl"
        write_jsonl(agent, [reply("w1", "2026-10-23T10:00:20Z", write=900, out=8, stop=None),
                            reply("w1", "2026-10-23T10:00:20Z", write=900, out=8, stop=None),
                            {"type": "assistant", "timestamp": "2026-10-23T10:00:21Z", "uuid": "syn",
                             "isApiErrorMessage": True, "message": {"model": "<synthetic>", "usage": {}}}])
        agent.with_name("agent-w1.meta.json").write_text(json.dumps({"agentType": "workflow-subagent",
                                                                     "description": "find:x"}), encoding="utf-8")
        res = usage.gather(self.transcript, usage.parse_ts("2026-10-23T10:00:00Z"))
        self.assertEqual((res["run"]["agents"], res["run"]["all_output_partial"]), (2, 1))
        self.assertIn("workflow-subagent: find:x", [a["label"] for a in res["run"]["top"]])
        out = self.run_usage("report", "--since", "2026-10-23T10:00:00Z").stdout
        self.assertIn("output ≥75", out)
        self.assertIn("`/usage` has the exact totals", out)

    def test_compactions_are_estimated_from_their_recorded_size(self):
        with open(self.transcript, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": "system", "subtype": "compact_boundary", "uuid": "c1",
                                 "timestamp": "2026-10-23T10:30:00Z", "compactMetadata": {"preTokens": 150000}}) + "\n")
        res = usage.gather(self.transcript, usage.parse_ts("2026-10-23T10:00:00Z"))
        self.assertEqual(res["run"]["all_compaction"], 150000)
        # An estimate shown on its own: the counted totals stay what the recorded replies used.
        self.assertEqual((res["run"]["total"], res["run"]["all_input"]), (1162 + 508, 3))
        self.assertEqual(res["session"]["main"]["total"], 2212)
        self.assertEqual(res["context"]["used"], 1162)  # a compaction isn't a reply: the context is still the last one
        self.assertIn("compaction ~150k (estimate, not in the total)", "\n".join(usage.report_lines(res, 0)))

    def test_session_and_run_totals(self):
        since = usage.parse_ts("2026-10-23T10:00:00Z")
        res = usage.gather(self.transcript, since)
        self.assertEqual(res["session"]["main"], {"input": 12, "cache_write": 1100, "cache_read": 1000,
                                                  "output": 100, "total": 2212, "output_partial": 0,
                                                  "compaction": 0})
        self.assertEqual((res["session"]["agents"], res["session"]["agents_total"]), (2, 508 + 103))
        self.assertEqual(res["session"]["total"], 2212 + 611)
        run = res["run"]
        self.assertEqual((run["main"]["total"], run["agents"], run["total"]), (1162, 1, 1162 + 508))
        self.assertEqual(run["top"][0]["label"], "bosun:code-reviewer: Review correctness")
        # Context is what the last main response read and wrote: 2 + 100 + 1000 + 60.
        self.assertEqual(res["context"], {"used": 1162, "window": usage.DEFAULT_WINDOW, "window_assumed": True})

    def test_the_window_follows_the_model_then_the_setting(self):
        write_jsonl(self.transcript, [reply("big", "2026-10-23T11:00:00Z", read=250_000, out=10)])
        self.assertEqual(usage.gather(self.transcript)["context"]["window"], usage.LARGE_WINDOW)
        for model, window in (("claude-opus-5-5", usage.LARGE_WINDOW), ("claude-sonnet-4-5", usage.DEFAULT_WINDOW),
                              ("claude-opus-4-7", usage.LARGE_WINDOW), ("claude-haiku-4-5-20251001", usage.DEFAULT_WINDOW)):
            write_jsonl(self.transcript, [reply("m", "2026-10-23T11:00:00Z", read=150_000, model=model)])
            self.assertEqual(usage.gather(self.transcript)["context"]["window"], window, model)
        ctx = usage.gather(self.transcript, window=500_000)["context"]
        self.assertEqual((ctx["window"], ctx["window_assumed"]), (500_000, False))
        env = dict(self.env, CLAUDE_CODE_MAX_CONTEXT_TOKENS="300000")
        self.assertIn("of 300k used", self.run_usage("report", env=env).stdout)

    def test_finds_the_newest_transcript_for_this_directory(self):
        older = self.folder / "sess-0.jsonl"
        write_jsonl(older, [reply("x", "2026-10-22T09:00:00Z", out=1)])
        os.utime(older, (1, 1))
        self.assertEqual(usage.find_transcript(cwd=self.project), self.transcript)
        sub = self.project / "src" / "deep"
        sub.mkdir(parents=True)
        self.assertEqual(usage.find_transcript(cwd=sub), self.transcript)  # a parent's folder counts
        env = dict(self.env, CLAUDE_CODE_SESSION_ID="sess-0")
        out = self.run_usage("report", "--json", env=env).stdout
        self.assertEqual(json.loads(out)["transcript"], str(older))  # the session id wins over the newest file

    def test_cli_start_and_report(self):
        start = self.run_usage("start").stdout.splitlines()
        self.assertRegex(start[0], r"^mark: \d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertIn("session so far: 2.8k tokens (2 agent(s))", start[1])
        out = self.run_usage("report", "--since", "2026-10-23T10:00:00Z", "--agents", "1").stdout
        self.assertIn("this run:** 1.7k across the main session and 1 agent(s)", out)
        self.assertIn("plan limits left: run `/usage`", out)
        self.assertIn("   - 508 (output 7): bosun:code-reviewer: Review correctness", out)
        data = json.loads(self.run_usage("report", "--json", "--agents", "1").stdout)
        self.assertIsNone(data["run"])
        self.assertEqual(data["session"]["total"], 2823)
        self.assertEqual([a["label"] for a in data["top"]], ["bosun:code-reviewer: Review correctness"])

    def test_a_named_session_without_a_file_is_an_error(self):
        # Not someone else's numbers: with persistence off, the id is set but there is no transcript.
        proc = self.run_usage("report", env=dict(self.env, CLAUDE_CODE_SESSION_ID="gone"), check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("no transcript for session gone", proc.stderr)
        other = self.base / "work" / "my-app-2"
        other.mkdir()
        proc = self.run_usage("report", cwd=other, check=False)  # my-app's transcript is not my-app-2's
        self.assertEqual(proc.returncode, 1)

    def test_output_survives_a_non_utf8_pipe(self):
        out = self.run_usage("report", env=dict(self.env, PYTHONIOENCODING="cp1252")).stdout
        self.assertIn("🧠", out)

    def test_bad_input_fails_clearly(self):
        proc = self.run_usage("report", "--since", "yesterday", check=False)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("ISO time", proc.stderr)
        empty = dict(self.env, CLAUDE_CONFIG_DIR=str(self.base / "nothing"))
        proc = self.run_usage("report", env=empty, check=False)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("--transcript", proc.stderr)


if __name__ == "__main__":
    unittest.main()
