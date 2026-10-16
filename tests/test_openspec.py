"""Tests for the OpenSpec support in taskboard.py (run: python3 -m unittest discover -s tests)."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins" / "bosun" / "scripts" / "taskboard.py"
EXAMPLE = ROOT / "examples" / "openspec-todo-api"
CHANGE = "openspec/changes/add-todo-api"
BOARD = ".bosun/plans/add-todo-api/tasks.json"

spec = importlib.util.spec_from_file_location("taskboard", SCRIPT)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)

MAIN_SPEC = """# todo-items Specification

## Purpose
Lets each signed-in user keep a private list of todo items and work through it.

## Requirements

### Requirement: Create todo item
The system SHALL create a todo item when given a non-empty title.

#### Scenario: Valid title
- **WHEN** a user creates a todo titled "Buy milk"
- **THEN** the system returns 201

#### Scenario: Empty title
- **WHEN** a user creates a todo with an empty title
- **THEN** the system returns 422

### Requirement: Archive todo items
The system SHALL hide archived items from the default list.

#### Scenario: Archived item hidden
- **WHEN** a user archives an item
- **THEN** the default list no longer shows it
"""


class TaskLineTests(unittest.TestCase):
    def test_task_line_rules_match_openspec(self):
        self.assertIsNotNone(tb.os_task("- [ ] 1.1 do it"))
        self.assertIsNotNone(tb.os_task("  * [x] 1.2 nested"))
        self.assertIsNotNone(tb.os_task("1. [ ] 1.3 ordered"))
        self.assertIsNotNone(tb.os_task("- [ ](not-a-link) whitespace box still counts"))
        self.assertIsNone(tb.os_task("- [x](https://example.com) link"))
        self.assertIsNone(tb.os_task("- [Some doc](./doc.md)"))
        self.assertIsNone(tb.os_task("- plain bullet"))

    def test_parse_tasks_md(self):
        text = "# Tasks\n\n## 1. Setup\n\n- [ ] 1.1 a\n- [ x ] 1.2 b\n- [~] 1.3 c\n- [X] no id\n\n## Notes\n- [ ] 2.1 d\n"
        tasks = tb.parse_tasks_md(text)
        self.assertEqual([t["id"] for t in tasks], ["1.1", "1.2", "1.3", None, "2.1"])
        self.assertEqual([t["done"] for t in tasks], [False, True, False, True, False])
        self.assertEqual(tasks[0]["group"], "1")
        self.assertIsNone(tasks[4]["group"])

    def test_fenced_requirements_are_ignored(self):
        delta = tb.parse_delta("## ADDED Requirements\n\n```\n### Requirement: Fake\n```\n\n"
                               "### Requirement: Real\nThe system SHALL work.\n\n#### Scenario: S\n- **WHEN** x\n- **THEN** y\n",
                               "specs/x/spec.md")
        self.assertEqual([r["name"] for r in delta["added"]], ["Real"])
        self.assertEqual(delta["added"][0]["scenarios"], ["S"])


class ExampleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        shutil.copytree(EXAMPLE, self.root)
        self.board = self.root / BOARD
        self.change = self.root / CHANGE

    def tearDown(self):
        self.tmp.cleanup()

    def run_tb(self, *args, check=True):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=self.root,
                              capture_output=True, text=True, timeout=60)
        if check and proc.returncode != 0:
            self.fail(f"taskboard {args} failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
        return proc

    def check(self):
        return tb.spec_check(json.loads(self.board.read_text()), self.board)

    def edit_board(self, fn):
        data = json.loads(self.board.read_text())
        fn(data)
        self.board.write_text(json.dumps(data))

    def write(self, rel, text):
        path = self.change / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def assert_error(self, errors, needle):
        self.assertTrue(any(needle in e for e in errors), f"{needle!r} not in {errors}")

    # --------------------------------------------------------------------- spec-check

    def test_example_passes(self):
        errors, warnings, report = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(report["requirements"], 8)
        self.assertEqual(report["uncovered"], [])
        self.assertIn("OK: change add-todo-api", self.run_tb("spec-check", str(self.board)).stdout)

    def test_uncovered_and_unknown_refs(self):
        def drop(data):
            for t in data["tasks"]:
                if t["id"] == "3.2":
                    t["spec_refs"] = ["todo-items#delete todo item", "todo-items"]
        self.edit_board(drop)
        errors, _, report = self.check()
        self.assert_error(errors, "'todo-items#Update and complete todo item' (ADDED) is not covered")
        self.assert_error(errors, "did you mean 'todo-items#Delete todo item'")
        self.assert_error(errors, "must look like '<capability>#<Requirement name>'")
        self.assertEqual(self.run_tb("spec-check", str(self.board), check=False).returncode, 1)

    def test_requirement_format_errors(self):
        self.write("specs/billing/spec.md",
                   "## Purpose\nLets paying customers be charged for their subscriptions each month.\n\n"
                   "## ADDED Requirements\n\n### Requirement: Charge card\nThe system charges the card.\n\n"
                   "### Scenario: wrong level\n- **WHEN** x\n- **THEN** y\n\n"
                   "### Requirement: Long\nThe system SHALL " + "x" * 520 + "\n\n#### Scenario: s\n- **WHEN** a\n")
        errors, _, _ = self.check()
        self.assert_error(errors, "'Charge card': requirement text needs SHALL or MUST")
        self.assert_error(errors, "'Charge card' needs at least one '#### Scenario:' with content (scenarios need exactly four #")
        self.assert_error(errors, "requirement text is 5")

    def test_stray_text_and_orphans(self):
        self.write("specs/notes/spec.md",
                   "# Spec Delta\n\nIntro prose.\n\n## Purpose\nNotes capability used to test stray text detection here.\n\n"
                   "## ADDED Requirements\n\nSome prose first.\n\n### Requirement: R\nThe system SHALL r.\n\n"
                   "#### Scenario: s\n- **WHEN** a\n- **THEN** b\n\n## Notes\n\n### Requirement: Lost\nThe system SHALL x.\n")
        errors, _, _ = self.check()
        self.assert_error(errors, "text above the first '## ' section")
        self.assert_error(errors, "text before the first requirement in '## ADDED Requirements'")
        self.assert_error(errors, "section '## Notes'")
        self.assert_error(errors, "requirement 'Lost' is outside the delta sections")

    def test_deltas_against_main_spec(self):
        main = self.root / "openspec" / "specs" / "todo-items" / "spec.md"
        main.parent.mkdir(parents=True)
        main.write_text(MAIN_SPEC)
        self.write("specs/todo-items/spec.md",
                   "## ADDED Requirements\n\n### Requirement: Create todo item\nThe system SHALL dup.\n\n"
                   "#### Scenario: s\n- **WHEN** a\n- **THEN** b\n\n"
                   "## MODIFIED Requirements\n\n### Requirement: Archive todo items\nThe system SHALL hide archived items.\n\n"
                   "#### Scenario: Other\n- **WHEN** a\n- **THEN** b\n\n"
                   "### Requirement: Ghost\nThe system SHALL haunt.\n\n#### Scenario: s\n- **WHEN** a\n- **THEN** b\n\n"
                   "## REMOVED Requirements\n\n### Requirement: Never existed\n\n"
                   "## RENAMED Requirements\n\n- FROM: `### Requirement: Create todo item`\n")
        errors, warnings, _ = self.check()
        self.assert_error(errors, "ADDED 'Create todo item' already exists in the main spec")
        self.assert_error(errors, "MODIFIED 'Ghost' does not exist in the main spec")
        self.assert_error(warnings, "REMOVED 'Never existed' does not exist in the main spec")
        self.assert_error(errors, "RENAMED FROM: 'Create todo item' has no matching TO: line")
        self.assert_error(errors, "drops scenario(s) 'Archived item hidden'")

    def test_new_capability_can_only_add(self):
        self.write("specs/reports/spec.md",
                   "## MODIFIED Requirements\n\n### Requirement: R\nThe system SHALL r.\n\n#### Scenario: s\n- **WHEN** a\n- **THEN** b\n")
        errors, warnings, _ = self.check()
        self.assert_error(errors, "has no main spec yet, so it can only ADD requirements")
        self.assert_error(warnings, "new capability without a '## Purpose'")

    def test_skip_specs(self):
        shutil.rmtree(self.change / "specs")
        errors, _, _ = self.check()
        self.assert_error(errors, "no delta specs under specs/")
        (self.change / ".openspec.yaml").write_text("schema: spec-driven\nskip_specs: true\n")
        self.edit_board(lambda d: [t.pop("spec_refs", None) for t in d["tasks"]])
        errors, _, _ = self.check()
        self.assertEqual(errors, [])

    def test_tasks_md_and_board_must_match(self):
        md = self.change / "tasks.md"
        md.write_text(md.read_text().replace("- [ ] 4.1", "- [ ] 4.2").replace("## 3. Todo items\n",
                                                                                 "## 3. Todo items\n\n- [ ] 2.9 misplaced\n"))
        errors, _, _ = self.check()
        self.assert_error(errors, "tasks.md task 4.2 is not on the board")
        self.assert_error(errors, "board task 4.1 has no line in tasks.md")
        self.assert_error(errors, "task 2.9 sits under group 3")

    # --------------------------------------------------------------------- tasks.md sync

    def test_set_ticks_and_unticks(self):
        md = self.change / "tasks.md"
        self.run_tb("set", str(self.board), "1.1", "1.2", "--status", "done")
        self.assertIn("- [x] 1.1 ", md.read_text())
        self.assertIn("- [x] 1.2 ", md.read_text())
        self.run_tb("set", str(self.board), "1.2", "--status", "pending")
        self.assertIn("- [ ] 1.2 ", md.read_text())
        self.run_tb("set", str(self.board), "2.1", "--status", "skipped")
        self.assertIn("- [ ] 2.1 ", md.read_text())  # skipped is not done: left alone
        errors, warnings, report = self.check()
        self.assertEqual(errors, [])
        self.assertEqual(report["tasks_md"], {"total": 8, "ticked": 1})

    def test_sync_repairs_drift_and_keeps_crlf(self):
        md = self.change / "tasks.md"
        md.write_bytes(md.read_bytes().replace(b"\n", b"\r\n").replace(b"- [ ] 3.1", b"- [x] 3.1"))
        _, warnings, _ = self.check()
        self.assert_error(warnings, "differ from the board for 3.1")
        self.assertIn("would update 1", self.run_tb("sync", str(self.board), "--dry-run").stdout)
        self.assertIn(b"- [x] 3.1", md.read_bytes())
        self.run_tb("sync", str(self.board))
        data = md.read_bytes()
        self.assertIn(b"- [ ] 3.1", data)
        self.assertNotIn(b"\r\r", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_add_appends_to_tasks_md(self):
        md = self.change / "tasks.md"
        self.run_tb("add", str(self.board), "--id", "3.3", "--title", "Rate-limit creation", "--deps", "3.1",
                    "--files", "src/rate.ts", "--acceptance", "429 after 60/min", "--spec-ref", "todo-items#Create todo item")
        self.run_tb("add", str(self.board), "--id", "5.1", "--title", "Fix flaky e2e", "--deps", "4.1",
                    "--files", "tests/e2e/x.ts", "--acceptance", "green")
        text = md.read_text()
        self.assertLess(text.index("- [ ] 3.3 Rate-limit creation"), text.index("## 4. Integration"))
        self.assertLess(text.index("## 5. Follow-up"), text.index("## Workflow follow-up"))
        self.assertNotIn("\n\n\n", text)
        bad = self.run_tb("add", str(self.board), "--id", "T9", "--title", "x", check=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("tasks.md ids", bad.stderr)
        errors, _, _ = self.check()
        self.assertEqual(errors, [])

    def test_brief_quotes_requirements(self):
        out = self.run_tb("brief", str(self.board), "3.1").stdout
        self.assertIn("OpenSpec change (read-only for you)", out)
        self.assertIn("### Requirement: Todo items are private", out)
        self.assertIn("#### Scenario: Another user's item", out)
        self.assertNotIn("PLAN.md", out)

    def test_status_reports_archived_change(self):
        archive = self.root / "openspec" / "changes" / "archive" / "2026-10-16-add-todo-api"
        archive.parent.mkdir(parents=True)
        shutil.move(str(self.change), str(archive))
        out = self.run_tb("status", str(self.board)).stdout
        self.assertIn("archived:", out)
        proc = self.run_tb("set", str(self.board), "1.1", "--status", "done")
        self.assertIn("archived", proc.stderr)
        errors, _, _ = self.check()
        self.assert_error(errors, "it was archived to")


@unittest.skipUnless(shutil.which("openspec"), "OpenSpec CLI not installed")
class OpenSpecCliTests(unittest.TestCase):
    def test_example_passes_openspec_validate(self):
        env = dict(os.environ, OPENSPEC_TELEMETRY="0")
        proc = subprocess.run(["openspec", "validate", "add-todo-api", "--strict", "--no-interactive"],
                              cwd=EXAMPLE, capture_output=True, text=True, timeout=120, env=env)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
