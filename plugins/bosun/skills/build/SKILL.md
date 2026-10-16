---
name: build
description: Execute a bosun plan with a pool of parallel agents. Schedules tasks by dependencies and file ownership, runs each implementer in its own git worktree, gates every task with code review (plus security review when sensitive), merges into an integration branch, monitors progress, and resumes after interruptions. Use after /bosun:plan, for ad-hoc task boards, or to resume a build.
argument-hint: "[plan-slug|board-path] [--parallel N] [--isolation worktree|shared] [--review task|batch|final] [--resume] [--only T01,T02] [--dry-run]"
---

# bosun build

Arguments: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"` (use `python` if `python3` is missing). The board (tasks.json) is the source of truth, and **you are its only writer**: subagents never edit it. Prefer one TB call with several ids over several parallel TB calls. Edge cases (shared mode, merge conflicts, resume, review policies) are covered in [reference/execution.md](reference/execution.md); read it when you hit one.

## 0. Preflight (stop and ask about anything red)

1. **Board.** Resolve the argument (slug, directory or path), else `TB latest`. Run `TB validate <board>`; errors mean stop.
2. **Settings.** Read `.bosun/config.json`. Defaults when absent: `build.max_parallel` 4, `isolation` worktree, `review` task, `security_review` sensitive, `max_attempts` 2, `merge` merge. Flags override. Note `commands` (install, test, lint, typecheck, build).
3. **Git** (worktree mode):
   - The working tree must be clean apart from ignored files and `.bosun/` (`git status --porcelain`). Otherwise ask the user to commit or stash first. Never stash for them.
   - Work branch: if `meta.work_branch` exists, switch to it. Otherwise, on the default branch create `bosun/<plan-name>`; on another branch, use that branch. Record it: `TB meta <board> --set work_branch=<b> --set base_branch=<default> --set base_commit=<sha> --set isolation=<mode> --set max_parallel=<N>`.
   - Worktree base: subagent worktrees must branch from the current HEAD, not the default branch, or tasks won't see the dependencies merged before them. Check `worktree.baseRef` in `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json`. If it isn't `"head"`: explain, and offer either to add it to `.claude/settings.local.json` and restart the session, or to continue in shared mode.
   - Not a git repository: shared mode.
4. **Resume** (`--resume`, or tasks already `in_progress`/`review`): agents from an earlier session are gone. For each such task, look for its branch or worktree (board fields `branch` and `worktree`, `git worktree list`). Commits present: set it to `review` and run the gate (section 2, step 3). Otherwise: `TB set <board> <ids> --status pending --note "reset on resume"`.
5. **Confirm.** Show tasks remaining, the `TB waves <board> --parallel <N>` summary, parallelism, isolation, review policy and work branch. Ask for a go-ahead unless the user already approved this build. With `--dry-run`, also print the prompt for the first wave, then stop.

## 1. Scheduling loop (rolling pool)

Repeat until nothing is pending or in flight:

1. `TB next <board> --parallel <N> --json` (add `--strict-files` in shared mode). It returns tasks whose deps are finished and whose files don't overlap work in flight, critical path first. With `--only`, ignore tasks not listed. `stuck: true` means go to section 3.
2. For each task to start, get its brief with `TB brief <board> <id>`. Mark them all in one call: `TB set <board> <ids...> --status in_progress --assignee <agent>`.
3. Launch them **in one message**, one Agent call per task:
   - `subagent_type`: the task's agent (`bosun:implementer` unless the task says otherwise);
   - `isolation: "worktree"` for code tasks in worktree mode (omit it for report tasks and in shared mode);
   - `name`: the task id in lowercase (for example `t07`), so you can message the agent later; `description`: "T07 <short title>";
   - `prompt`: the template below.
4. Agents run in the background and you're notified as each finishes. Process each result right away (section 2) and refill the pool from step 1. Don't wait for a whole wave. If your agents run in the foreground instead, process the batch when it returns, then continue.
5. About every 5 finished tasks, print one progress line from `TB status <board>`. About every 10 finished tasks, or after two failures in a row, spawn `bosun:monitor` with the board's absolute path and act on its recommendations.

Prompt template (fill it in, keep it short):

```
You are working on task <ID> of the bosun plan "<plan title>".
Mode: <worktree: you are in your own git worktree, on your own branch created from the work branch "<work_branch>". Commit your work there. Never push.
      | shared: you are in the main checkout with other agents. Edit only your owned files. Don't stage or commit.>
Main checkout (read-only reference): <absolute path>
Project commands: install=<...> test=<...> lint=<...> typecheck=<...> build=<...>

<output of TB brief>

<retries only: what went wrong last time and what to do differently>
End with your BOSUN-RESULT block.
```

## 2. Per-task pipeline

1. **Read the result.** `done` continues below. `partial`, `failed`, `blocked`, `needs_input`, or no result block: section 3.
2. **Spot-check** (code tasks, worktree mode). `git log --oneline <work_branch>..<task_branch>` shows its commits; `git diff --stat <work_branch>...<task_branch>` touches only expected files. If its worktree has uncommitted changes that belong to the task, commit them there yourself (`git -C <worktree> add -A`, then `git -C <worktree> commit -m "<type>(<ID>): <summary>"`). Out-of-scope files: accept with a note, or send the task back. Then `TB set <board> <ID> --status review --branch <task_branch> --worktree <path>`.
3. **Gate** (review policy `task`; for `batch` and `final` see the reference). In one message spawn:
   - `bosun:code-reviewer` with lens `correctness`, plus a second one with lens `tests` when the task's risk is high;
   - `bosun:security-reviewer` in `diff` mode when the task is `security_sensitive`, when `security_review` is `always`, or (policy `sensitive`) when the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, permissions, secrets or config, or dependencies.
   Give each reviewer the task brief, the diff command `git diff <work_branch>...<task_branch>`, the worktree path for reading full files, and the project conventions.
4. **Decide.** Blocking means critical or high severity with medium or high confidence. If a blocking finding looks doubtful, have `bosun:verifier` check it first. Medium findings: fix in the same round if cheap, otherwise record a follow-up task with `TB add`. Low and nit: record only.
5. **Fix round** (at most two per task; after that, treat it as `blocked`). Send the confirmed blocking findings to the same implementer with SendMessage (`to` = its name) and ask it to fix them in its worktree, commit, and report a new result. If it can't be resumed, spawn a new implementer (worktree) whose prompt starts with "First run `git merge <task_branch>` to pick up the previous attempt", followed by the findings. Re-run only the reviewers that blocked.
6. **Merge** (you, in the main checkout, on the work branch): `git merge --no-ff -m "bosun(<ID>): <title>" <task_branch>` (squash instead if `build.merge` is `squash`). On conflict: `git merge --abort`, then follow the reference, section "Conflicts". In shared mode there is no branch: commit only the task's files instead (reference, section "Shared mode").
7. **Integration check.** After each merge, run the fast checks yourself (lint or typecheck, and the tests near the change). Run the full test suite about every 5 merges and whenever a schedule wave completes. If it goes red, find the culprit merge, undo it with `git revert -m 1 <merge_sha>` (never reset), and reopen the task with a note.
8. **Record and clean up.** `TB set <board> <ID> --status done --commit <merge_sha> --summary "<one line>"`. Then `git worktree remove <worktree>` and `git branch -d <task_branch>` (after a squash merge git can't tell the branch was merged, so use `-D` once you've confirmed the squash commit landed). Save the agent's result block and the reviewers' verdicts to `.bosun/plans/<name>/reports/<ID>.md`.

Report tasks (`kind: report`) are not merged: save the result to `reports/<ID>.md`, mark the task done with a one-line summary, and turn in-scope, actionable findings into new tasks with `TB add`.

## 3. When things go wrong

- No result block: inspect the agent's branch or files yourself. If the work is complete and the checks pass when you run them, continue with the spot-check (section 2, step 2); otherwise treat it as `partial`.
- `partial` or `failed`, attempts below `max_attempts`: `TB set <board> <ID> --status pending --note "<what to change>"`. The note appears in its next brief. For `partial` work worth keeping, put "start with `git merge <task_branch>`" in the note so the next attempt builds on it; remove the old worktree and branch once the retry has been merged.
- `needs_input`: ask the user (batch the questions) and keep other tasks moving. Record the answer as a note and set the task to pending.
- Attempts exhausted, or `blocked`: `TB set <board> <ID> --status blocked --note "<reason>"`. Tell the user once, with options: clarify, split the task, skip it (`--status skipped` lets dependents proceed), or take it over.
- Two tasks in a row failing the same way (broken install, a shared test failing on the work branch): stop dispatching, fix the work branch first, then resume.
- `stuck: true`: nothing can start. Resolve the blocked tasks with the user.

## 4. Finish

When the board is complete, or only blocked and skipped tasks remain:

1. Run the full checks yourself: install, lint, typecheck, test, build.
2. Final review: run the `bosun:review` skill on `<base_commit>...HEAD` with lenses correctness, design and tests. If any task was security-sensitive, also run `bosun:security-audit` on the same range.
3. Fix critical and high findings through the same pipeline (new tasks via `TB add`).
4. If the plan had no docs task, spawn `bosun:docs-writer` for the README and CHANGELOG.
5. Write `.bosun/plans/<name>/SUMMARY.md`: what was delivered, deviations from the plan, decisions made along the way, follow-ups, known issues, how to run it.
6. Tell the user the outcome in a few lines, separating what you verified from what you didn't. `/bosun:ship` pushes and opens the PR; never push yourself.
