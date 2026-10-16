---
name: build
description: Execute a bosun plan with a pool of parallel agents. Schedules tasks by dependencies and file ownership, runs each implementer in its own git worktree, gates every task with code review (plus security review when sensitive), merges into an integration branch, keeps an OpenSpec change's tasks.md in step, monitors progress, and resumes after interruptions. Use after /bosun:plan, for ad-hoc task boards, or to resume a build.
argument-hint: "[change-id|plan-slug|board-path] [--parallel N] [--isolation worktree|shared] [--review task|batch|final] [--resume] [--only 1.1,2.3] [--dry-run]"
---

# bosun build

Arguments: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"` (use `python` if `python3` is missing). The board (tasks.json) is the source of truth, and **you are its only writer**: subagents never edit it. Prefer one TB call with several ids over several parallel TB calls. Edge cases (shared mode, merge conflicts, resume, review policies) are covered in [reference/execution.md](reference/execution.md); read it when you hit one.

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, can, may, must); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

**OpenSpec plans** are boards with `meta.openspec_change`. The change in `openspec/changes/<id>/` is the contract: each brief quotes the requirements its task implements, `TB set --status done` ticks the task in tasks.md, and only the architect edits the change.

## 0. Preflight (stop and ask about anything red)

1. **Board.** Resolve the argument (change id, slug, directory or path), else `TB latest`. Run `TB validate <board>`; errors mean stop. OpenSpec plan: also `TB spec-check <board>`, and with the CLI `OPENSPEC_TELEMETRY=0 openspec validate <id> --strict --no-interactive`; errors mean stop.
2. **Settings.** Read `.bosun/config.json`. Defaults when absent: `build.max_parallel` 4, `isolation` worktree, `review` task, `security_review` sensitive, `max_attempts` 2, `merge` merge. Flags override. Note `commands` (install, test, lint, typecheck, build).
3. **Git** (worktree mode):
   - The working tree must be clean apart from ignored files, `.bosun/`, and (OpenSpec plan) the uncommitted plan files: the change directory, plus `openspec/config.yaml` if the plan created it. Otherwise ask the user to commit or stash first. Never stash for them. Exception: a merge that an interrupted build left in progress (`git rev-parse -q --verify MERGE_HEAD` succeeds, or after a squash the file at `git rev-parse --git-path SQUASH_MSG` exists). It isn't the user's work, and committing it skips the integration check while stashing it drops the merge, so don't ask about it: step 4 handles it (and asks if the merge matches no task).
   - Work branch: if `meta.work_branch` exists, switch to it. Otherwise, on the default branch create `bosun/<plan-name>`; on another branch, use that branch. Record it: `TB meta <board> --set work_branch=<b> --set base_branch=<default> --set base_commit=<sha> --set isolation=<mode> --set max_parallel=<N>`.
   - OpenSpec plan with uncommitted plan files: commit them on the work branch now (`git add -- <those paths>`, then `git commit -m "docs(spec): propose <id>"` in the repository's commit style). Worktrees contain only committed files, and implementers read the specs there.
   - Worktree base: subagent worktrees must branch from the current HEAD, not the default branch, or tasks won't see the dependencies merged before them. Check `worktree.baseRef` in `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json`. If it isn't `"head"`: explain, and offer either to add it to `.claude/settings.local.json` and restart the session, or to continue in shared mode.
   - Not a git repository: shared mode.
4. **Resume** (`--resume`, or tasks already `in_progress`/`review`): agents from an earlier session are gone. Decide now; act after the go-ahead in step 5:
   - A merge left in progress (step 3): settle it first (reference, "Resume details").
   - Find each task's work. A `review` task: the board fields `branch` and `worktree`. An `in_progress` task: those fields are written only at review, so they're missing or left over from an earlier attempt; look in `git worktree list` for the worktree with commits named `<type>(<ID>): ...` or uncommitted changes in the task's files. If you can't tell which worktree is the task's, don't guess: treat the task as having no work.
   - `review` with commits: run its gate (section 2, step 3) before dispatching new work.
   - `in_progress` with commits or uncommitted changes: the work may be unfinished. Commit the changes in its worktree (as in section 2, step 2), then retry it with an implementer whose prompt starts with "First run `git merge <task_branch>`" (reference, "Resume details").
   - No work: `TB set <board> <ids> --status pending --note "reset on resume"`.
   OpenSpec plan: if `TB status` reports tasks.md out of sync, run `TB sync <board>` and commit tasks.md.
5. **Confirm.** Show tasks remaining, the resume decisions from step 4 (including worktrees no task claimed), the `TB waves <board> --parallel <N>` summary, parallelism, isolation, review policy and work branch. Ask for a go-ahead before starting any agent, unless the user already approved this build. With `--dry-run`, also print the prompt for the first wave, then stop.

## 1. Scheduling loop (rolling pool)

Repeat until nothing is pending or in flight:

1. `TB next <board> --parallel <N> --json` (add `--strict-files` in shared mode). It returns tasks whose deps are finished and whose files don't overlap work in flight, critical path first. With `--only`, ignore tasks not listed. `stuck: true` means go to section 3.
2. For each task to start, get its brief with `TB brief <board> <id>`. Mark them all in one call: `TB set <board> <ids...> --status in_progress --assignee <agent>`.
3. Launch them **in one message**, one Agent call per task:
   - `subagent_type`: the task's agent (`bosun:implementer` unless the task says otherwise);
   - `isolation: "worktree"` for code tasks in worktree mode (omit it for report tasks and in shared mode);
   - `name`: the task id in lowercase with dots replaced (for example `t2-1` for task 2.1), so you can message the agent later; `description`: "2.1 <short title>";
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

1. **Read the result.** `done` continues below. `partial`, `failed`, `blocked`, `needs_input`, or no result block: section 3. Collect any `spec_gaps` for the final report; a gap that blocks correctness goes to the user before more dependent tasks start.
2. **Spot-check** (code tasks, worktree mode). `git log --oneline <work_branch>..<task_branch>` shows its commits; `git diff --stat <work_branch>...<task_branch>` touches only expected files (never `openspec/`). If its worktree has uncommitted changes that belong to the task, commit them there yourself (`git -C <worktree> add -A`, then `git -C <worktree> commit -m "<type>(<ID>): <summary>"`). Out-of-scope files: accept with a note, or send the task back. Then `TB set <board> <ID> --status review --branch <task_branch> --worktree <path>`.
3. **Gate** (review policy `task`; for `batch` and `final` see the reference). In one message spawn:
   - `bosun:code-reviewer` with lens `correctness`; for a task with `spec_refs`, a second one with lens `spec`; a reviewer with lens `tests` when the task's risk is high;
   - `bosun:security-reviewer` in `diff` mode when the task is `security_sensitive`, when `security_review` is `always`, or (policy `sensitive`) when the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, permissions, secrets or config, or dependencies.
   Give each reviewer the task brief, the diff command `git diff <work_branch>...<task_branch>`, the worktree path for reading full files, and the project conventions.
4. **Decide.** Blocking means critical or high severity with medium or high confidence. If a blocking finding looks doubtful, have `bosun:verifier` check it first. Medium findings: fix in the same round if cheap, otherwise record a follow-up task with `TB add` (OpenSpec plan: give it a tasks.md id such as `5.1`; TB adds the tasks.md line). Low and nit: record only.
5. **Fix round** (at most two per task; after that, treat it as `blocked`). Send the confirmed blocking findings to the same implementer with SendMessage (`to` = its name) and ask it to fix them in its worktree, commit, and report a new result. If it can't be resumed, spawn a new implementer (worktree) whose prompt starts with "First run `git merge <task_branch>` to pick up the previous attempt", followed by the findings. Re-run only the reviewers that blocked.
6. **Merge without committing** (you, in the main checkout, on the work branch): `git merge --no-ff --no-commit <task_branch>`, or `git merge --squash <task_branch>` if `build.merge` is `squash`. On conflict: `git merge --abort` (after a squash, `git reset --merge`), then follow the reference, section "Conflicts". In shared mode there is no branch: see the reference, section "Shared mode".
7. **Integration check** on the merged tree: the fast checks (lint or typecheck, and the tests near the change). Red: undo the merge (`git merge --abort`, or `git reset --merge` after a squash) and send the task back with the failure (`TB set <board> <ID> --status pending --note "<failure>"`).
8. **Record and commit.** `TB set <board> <ID> --status done --summary "<one line>"` (OpenSpec plan: this ticks the task in tasks.md; `git add -- <tasks.md path>` so the tick lands in the same commit). Then `git commit -m "bosun(<ID>): <title>"` and `TB set <board> <ID> --commit <sha>`.
9. **Full suite** about every 5 merges and whenever a schedule wave completes. If it goes red, find the culprit merge, undo it with `git revert -m 1 <merge_sha>` (`git revert <sha>` for a squash commit; never reset), and reopen the task with `TB set <board> <ID> --status pending --note "<failure>"`. The revert also unticks tasks.md; commit if `TB status` still reports drift after `TB sync`.
10. **Clean up.** `git worktree remove <worktree>` and `git branch -d <task_branch>` (after a squash merge git can't tell the branch was merged, so use `-D` once you've confirmed the squash commit landed). Save the agent's result block and the reviewers' verdicts to `.bosun/plans/<name>/reports/<ID>.md`.

Report tasks (`kind: report`) are not merged: save the result to `reports/<ID>.md`, mark the task done with a one-line summary, and turn in-scope, actionable findings into new tasks with `TB add`. OpenSpec plan: marking it done ticks tasks.md, so commit tasks.md (`git commit -m "bosun(<ID>): <title>" -- <tasks.md path>`).

## 3. When things go wrong

- No result block: inspect the agent's branch or files yourself. If the work is complete and the checks pass when you run them, continue with the spot-check (section 2, step 2); otherwise treat it as `partial`.
- `partial` or `failed`, attempts below `max_attempts`: `TB set <board> <ID> --status pending --note "<what to change>"`. The note appears in its next brief. For `partial` work worth keeping, put "start with `git merge <task_branch>`" in the note so the next attempt builds on it; remove the old worktree and branch once the retry has been merged.
- `needs_input`: ask the user (batch the questions) and keep other tasks moving. Record the answer as a note and set the task to pending. If the answer changes the spec, have `bosun:architect` revise the change (and re-run `TB spec-check`) before the task restarts.
- Attempts exhausted, or `blocked`: `TB set <board> <ID> --status blocked --note "<reason>"`. Tell the user once, with options: clarify, split the task, skip it (`--status skipped` lets dependents proceed and leaves its tasks.md line unticked), or take it over.
- Two tasks in a row failing the same way (broken install, a shared test failing on the work branch): stop dispatching, fix the work branch first, then resume.
- `stuck: true`: nothing can start. Resolve the blocked tasks with the user.

## 4. Finish

When the board is complete, or only blocked and skipped tasks remain:

1. Run the full checks yourself: install, lint, typecheck, test, build.
2. Final review: run the `bosun:review` skill on `<base_commit>...HEAD` with lenses correctness, design and tests, plus `spec` for an OpenSpec plan (every requirement in the change against the code and its tests). If any task was security-sensitive, also run `bosun:security-audit` on the same range.
3. Fix critical and high findings through the same pipeline (new tasks via `TB add`).
4. OpenSpec plan: `TB spec-check <board>` must be clean and every task line in tasks.md ticked; skipped tasks stay unticked, so ask the user whether to drop them from the change (architect, revise mode) or finish them. With the CLI, run `openspec validate <id> --strict --no-interactive` once more.
5. If the plan had no docs task, spawn `bosun:docs-writer` for the README and CHANGELOG.
6. Write `.bosun/plans/<name>/SUMMARY.md`: what was delivered (per requirement for an OpenSpec plan), deviations from the plan, spec gaps the agents reported, decisions made along the way, follow-ups, known issues, how to run it.
7. Tell the user the outcome in a few lines, separating what you verified from what you didn't. Next steps: `/bosun:ship` pushes and opens the PR (never push yourself); for an OpenSpec plan, `/bosun:archive <id>` merges the change into `openspec/specs/`. Archiving on the work branch before shipping lets the PR carry the updated specs; some teams archive after review instead.
