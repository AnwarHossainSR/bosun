---
name: build
description: Run a bosun plan with parallel agents in git worktrees: review-gated merges, tasks.md kept in step, resume. Use after /bosun:plan, for a task board, or to resume a build.
argument-hint: "[change-id|plan-slug|board-path] [--parallel N] [--isolation worktree|shared] [--review task|batch|final] [--resume] [--only 1.1,2.3] [--dry-run]"
---

# bosun build

Arguments: $ARGUMENTS

TB = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"` (`python` if `python3` is missing). The board (tasks.json) is the source of truth and **you are its only writer**; subagents never edit it. Prefer one TB call with several ids. Edge cases (shared mode, conflicts, resume, review policies): [reference/execution.md](reference/execution.md), read the section you need.

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Your context lasts the whole build; keep it small.** Agents read their own briefs. The SubagentStop hook saves each agent's final message to `.bosun/results/<time>-<agent>-<task>-<id>.md`: never copy result blocks into files (no file appears, as with an older Claude Code: save them to `.bosun/plans/<name>/reports/<ID>.md` yourself). Long commands go to a log you tail: `log=$(mktemp); <cmd> >"$log" 2>&1; echo "exit $?"; tail -n 40 "$log"`; read more only on failure.

**OpenSpec plans** are boards with `meta.openspec_change`; the change in `<openspec_dir>/changes/<id>/` is the contract. `<openspec_dir>` = `planning.openspec_dir` in `.bosun/config.json` (default `openspec`), the one setting the task board, the guard and these steps share; `TB status <board> --json` reports it resolved as `openspec.base`, and `TB brief` prints the change's absolute path. Briefs quote the requirements each task implements, `TB set --status done` ticks tasks.md, and only the architect edits the change. Run every `openspec` command from the OpenSpec directory's parent (repository root for `openspec`, `.bosun/` for `.bosun/openspec`): the CLI uses the nearest `openspec/` folder, so from elsewhere it can act on the wrong specs.

**Local OpenSpec directory:** one git ignores (`git check-ignore -q <openspec_dir>/changes` succeeds), such as `.bosun/openspec` beside a project's own OpenSpec. Its files never go into git: follow the *local* notes, which skip those git steps. Worktrees don't contain it; agents read the change from the main checkout via the absolute paths in `TB brief`.

## 0. Preflight (stop and ask about anything red)

1. **Board:** the argument (change id, slug, directory or path), else `TB latest`. `TB validate <board>`; OpenSpec plan: also `TB spec-check <board>` and, with the CLI (from the OpenSpec directory's parent), `OPENSPEC_TELEMETRY=0 openspec validate <id> --strict --no-interactive`. Errors mean stop.
2. **Settings:** `.bosun/config.json`; defaults when absent: `build.max_parallel` 4, `isolation` worktree, `review` task, `security_review` sensitive, `max_attempts` 2, `merge` merge. Flags override. Note `commands` (install, test, lint, typecheck, build).
3. **Git** (worktree mode):
   - Clean working tree apart from ignored files, `.bosun/` and (OpenSpec plan) the uncommitted plan files: the change directory, plus `<openspec_dir>/config.yaml` if the plan created it. Otherwise ask the user to commit or stash first; never stash for them. One exception, an unfinished merge (`git rev-parse -q --verify MERGE_HEAD` succeeds, or after a squash the file at `git rev-parse --git-path SQUASH_MSG` exists): its staged and conflicted paths (`git diff --name-only --diff-filter=U`) are step 4's. Don't ask to commit or stash them (committing skips the integration check, stashing drops the merge, and with conflicts git refuses both). Anything else in the tree still counts.
   - Work branch: `meta.work_branch` set and not current (`git branch --show-current`): switch to it. During an unfinished merge never switch or check out a branch and never run `git merge --quit` (`git checkout` of the current branch silently drops the merge state); HEAD not the work branch then: stop and ask. No work branch yet: on the default branch create `bosun/<plan-name>`, on another branch use it. Record: `TB meta <board> --set work_branch=<b> --set base_branch=<default> --set base_commit=<sha> --set isolation=<mode> --set max_parallel=<N>`.
   - OpenSpec plan whose `<openspec_dir>` is inside `.bosun/` but not git-ignored (`git check-ignore -q <openspec_dir>/changes` fails): stop and ask; it was meant to be local, and without an ignore rule the steps below would commit it.
   - Uncommitted plan files (*local: skip*): commit them on the work branch now (`git add -- <those paths>`, then `git commit -m "docs(spec): propose <id>"` in the repository's style). Worktrees hold only committed files, and implementers read the specs there.
   - Worktree base: subagent worktrees must branch from the current HEAD, not the default branch, or tasks miss the dependencies merged before them. Check `worktree.baseRef` in `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json`. Not `"head"`: explain, and offer to add it to `.claude/settings.local.json` and restart the session, or to continue in shared mode.
   - Not a git repository: shared mode.
4. **Resume** (`--resume`, tasks already `in_progress` or `review`, or an unfinished merge from step 3): agents from the earlier session are gone. Read the reference, section "Resume", and decide now for each task and the merge; act only after step 5's go-ahead. Tasks with no work: `TB set <board> <ids> --status pending --note "reset on resume"`. A merge left to the user: start section 1 only once it's settled (`git rev-parse -q --verify MERGE_HEAD` fails, `SQUASH_MSG` is gone, `git diff --cached --quiet` passes). OpenSpec plan: `TB status` reports tasks.md out of sync: `TB sync <board>`, then commit tasks.md (*local: skip the commit*).
5. **Confirm:** tasks remaining, resume decisions (including an unfinished merge, worktrees no task claimed, uncommitted paths outside a task), the `TB waves <board> --parallel <N>` summary, parallelism, isolation, review policy, work branch. Get a go-ahead before starting any agent unless the user already approved this build; an unfinished merge always needs one. `--dry-run`: also print the first wave's prompt, then stop.

## 1. Scheduling loop (rolling pool)

Until nothing is pending or in flight:

1. `TB next <board> --parallel <N> --json` (shared mode: add `--strict-files`): tasks whose deps are finished and whose files don't overlap work in flight, critical path first. With `--only`, ignore unlisted tasks. `stuck: true`: section 3.
2. Mark the tasks to start in one call: `TB set <board> <ids...> --status in_progress --assignee <agent>`.
3. Launch them **in one message**, one Agent call each: `subagent_type` = the task's agent (`bosun:implementer` unless it says otherwise); `isolation: "worktree"` for code tasks in worktree mode (not for report tasks or shared mode); `name` = the task id in lowercase with dots replaced (`t2-1` for 2.1), so you can message it later; `description` = "2.1 <short title>"; `prompt` = the template below.
4. Agents run in the background and you're notified as each finishes: process each result at once (section 2) and refill from step 1; don't wait for a whole wave. Foreground agents: process the batch when it returns, then continue.
5. About every 5 finished tasks print one progress line from `TB status <board>`. About every 10, or after two failures in a row, spawn `bosun:monitor` with the board's absolute path and act on its recommendations.

Prompt template (keep it short; bosun agents get the project commands and output style from the startup hook):

```
Task <ID> of bosun plan "<plan title>". Read your brief first: <TB> brief <absolute board path> <ID>
Mode: <worktree: your own git worktree on your own branch, created from the work branch "<work_branch>". Commit there. Never push.
      | shared: the main checkout, with other agents. Edit only your owned files. Don't stage or commit.>
Main checkout (read-only reference): <absolute path>
<retries only: what went wrong last time and what to do differently>
```

An agent from outside bosun (the user's `.claude/agents/` or another plugin) gets neither the hook nor bosun's instructions: paste the brief and the project commands into its prompt and ask it to end with a `# BOSUN-RESULT` block (status, summary, branch, commit).

## 2. Per-task pipeline

1. **Result:** `done` continues. `partial`, `failed`, `blocked`, `needs_input` or no result block: section 3. Collect `spec_gaps` for the final report; a gap that blocks correctness goes to the user before more dependent tasks start.
2. **Spot-check** (code tasks, worktree mode): `git log --oneline <work_branch>..<task_branch>` shows its commits; `git diff --stat <work_branch>...<task_branch>` touches only expected files (never the OpenSpec directory, nor a project's own `openspec/`). Uncommitted changes in its worktree that belong to the task: commit them there (`git -C <worktree> add -A`, then `git -C <worktree> commit -m "<type>(<ID>): <summary>"`). Out-of-scope files: accept with a note, or send the task back. Then `TB set <board> <ID> --status review --branch <task_branch> --worktree <path>`.
3. **Gate** (review policy `task`; `batch` and `final`: reference). Lenses: `correctness`; `spec` for a task with `spec_refs`; `tests` when its risk is high. A diff under about 200 changed lines (`git diff --shortstat <work_branch>...<task_branch>`) gets one `bosun:code-reviewer` for all its lenses, a larger one a reviewer per lens. In the same message add `bosun:security-reviewer` in `diff` mode when the task is `security_sensitive`, `security_review` is `always`, or (policy `sensitive`) the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, permissions, secrets or config, or dependencies. Each reviewer gets the board path and task id (it reads the brief), the diff command `git diff <work_branch>...<task_branch>`, the worktree path for full files, and its lens or lenses.
4. **Decide:** blocking = critical or high severity with medium or high confidence; have `bosun:verifier` check a doubtful one first. Medium: fix in the same round if cheap, else a follow-up task via `TB add` (OpenSpec plan: a tasks.md id such as `5.1`; TB adds the tasks.md line). Low and nit: record only.
5. **Fix round** (two per task at most, then treat it as `blocked`): send the confirmed blocking findings to the same implementer with SendMessage (`to` = its name) to fix in its worktree, commit and report again. Can't be resumed: spawn a new implementer (worktree) whose prompt starts with "First run `git merge <task_branch>` to pick up the previous attempt", then the findings. Re-run only the reviewers that blocked.
6. **Merge without committing** (you, main checkout, work branch). First check nothing is pending: `git rev-parse -q --verify MERGE_HEAD` fails, `SQUASH_MSG` doesn't exist, `git diff --cached --quiet` passes; otherwise stop, because a squash merge would stack on the leftovers and commit them under this task. Then `git merge --no-ff --no-commit <task_branch>`, or `git merge --squash <task_branch>` if `build.merge` is `squash`. Conflict: `git merge --abort` (after a squash, `git reset --merge`), then the reference, "Conflicts". Shared mode has no branch: reference, "Shared mode".
7. **Integration check** on the merged tree: the fast checks (lint or typecheck, tests near the change). Red: undo the merge (`git merge --abort`, or `git reset --merge` after a squash) and send the task back (`TB set <board> <ID> --status pending --note "<failure>"`).
8. **Record and commit:** `TB set <board> <ID> --status done --summary "<one line>"` (OpenSpec plan: this ticks tasks.md; `git add -- <tasks.md path>` so the tick lands in the same commit, *local: skip the add*). Then `git commit -m "bosun(<ID>): <title>"` and `TB set <board> <ID> --commit <sha>`.
9. **Full suite** about every 5 merges and whenever a schedule wave completes. Red: find the culprit merge, undo it with `git revert -m 1 <merge_sha>` (`git revert <sha>` for a squash commit; never reset), and reopen the task (`TB set <board> <ID> --status pending --note "<failure>"`). The revert unticks tasks.md too; commit if `TB status` still reports drift after `TB sync` (*local*: the revert leaves tasks.md alone, the `TB set` unticks it, nothing to commit).
10. **Clean up:** `git worktree remove <worktree>`, `git branch -d <task_branch>` (after a squash merge git can't tell the branch was merged: `-D` once you've confirmed the squash commit landed). Results are already in `.bosun/results/`; write `.bosun/plans/<name>/reports/<ID>.md` only for notes of your own (a decision, why you accepted a finding).

Report tasks (`kind: report`) aren't merged: mark the task done with a one-line summary (the result is in `.bosun/results/`) and turn in-scope, actionable findings into tasks with `TB add`. OpenSpec plan: marking it done ticks tasks.md, so commit tasks.md (`git commit -m "bosun(<ID>): <title>" -- <tasks.md path>`; *local: skip*).

## 3. When things go wrong

- No result block: inspect the agent's branch or files yourself. Complete, and its checks pass when you run them: continue at the spot-check (section 2, step 2); otherwise treat it as `partial`.
- `partial` or `failed`, attempts below `max_attempts`: `TB set <board> <ID> --status pending --note "<what to change>"`; the note appears in its next brief. `partial` work worth keeping: put "start with `git merge <task_branch>`" in the note so the next attempt builds on it; remove the old worktree and branch once the retry is merged.
- `needs_input`: ask the user (batch the questions) and keep other tasks moving. Record the answer as a note and set the task to pending. An answer that changes the spec: have `bosun:architect` revise the change (and re-run `TB spec-check`) before the task restarts.
- Attempts exhausted, or `blocked`: `TB set <board> <ID> --status blocked --note "<reason>"`. Tell the user once, with options: clarify, split the task, skip it (`--status skipped` lets dependents proceed and leaves its tasks.md line unticked), or take it over.
- Two tasks in a row failing the same way (broken install, a shared test failing on the work branch): stop dispatching, fix the work branch, then resume.
- `stuck: true`: nothing can start; resolve the blocked tasks with the user.

## 4. Finish

When the board is complete, or only blocked and skipped tasks remain:

1. Run the full checks yourself: install, lint, typecheck, test, build.
2. Final review: the `bosun:review` skill on `<base_commit>...HEAD` with lenses correctness, design and tests, plus `spec` for an OpenSpec plan (every requirement in the change against the code and its tests). Any task security-sensitive: also `bosun:security-audit` on the same range.
3. Fix critical and high findings through the same pipeline (new tasks via `TB add`).
4. OpenSpec plan: `TB spec-check <board>` clean and every task line in tasks.md ticked. Skipped tasks stay unticked: ask whether to drop them from the change (architect, revise mode) or finish them. With the CLI, `openspec validate <id> --strict --no-interactive` once more, from the OpenSpec directory's parent.
5. No docs task in the plan: spawn `bosun:docs-writer` for the README and CHANGELOG.
6. Write `.bosun/plans/<name>/SUMMARY.md` from the board, `.bosun/results/` and your notes: what was delivered (per requirement for an OpenSpec plan), deviations from the plan, spec gaps the agents reported, decisions made along the way, follow-ups, known issues, how to run it.
7. Tell the user the outcome in a few lines, separating what you verified from what you didn't. Next: `/bosun:ship` pushes and opens the PR (never push yourself); OpenSpec plan: `/bosun:archive <id>` merges the change into `<openspec_dir>/specs/`. Archiving on the work branch before shipping lets the PR carry the updated specs; some teams archive after review instead. A local OpenSpec directory never reaches the PR.
