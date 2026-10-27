---
name: status
description: Show a bosun build's progress, blocked tasks and next steps; --audit adds a health check. Use for build status.
argument-hint: "[plan-slug|board-path] [--audit]"
disable-model-invocation: true
model: haiku
---

# bosun status

Arguments: $ARGUMENTS

TB = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`.

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

1. **Board:** the argument, else `TB latest`. None: say there's no bosun plan in this repository and suggest `/bosun:propose` (or `/bosun:plan`) or `/bosun:manager`.
2. **Gather:** `TB status <board>`, `TB activity <board> --tail 10`, `git branch --show-current`, `git worktree list`.
3. **Compact dashboard:** the progress line and route (solo or crew; a solo run's progress is its task commits, `git log --oneline <work_branch>..<its branch>`, since its tasks are marked done together); for an OpenSpec plan, the change and its tasks.md progress (drift reported: suggest `TB sync <board>`); tasks in flight (task, agent, elapsed time); blocked or failed tasks with their last note; the next ready tasks; notable recent events. No raw JSON.
4. **Audit** with `--audit`, or when something looks off (a task in flight much longer than the others, repeated failures, `STUCK`, worktrees with no matching in-flight task): spawn `bosun:monitor` with the board's absolute path, then show its health verdict and recommended actions.
5. **Change nothing.** To act on a recommendation, suggest the command (`/bosun:apply <plan> --resume`, the same as `/bosun:build`, or the specific TB or git step), or run it once the user says so.
