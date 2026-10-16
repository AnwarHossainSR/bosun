---
name: status
description: Show the progress of a bosun build - finished, in-flight and blocked tasks, what's next, recent agent activity and git state - and optionally a health audit by the monitor agent. Use when the user asks about status, progress, what's running or what's blocked.
argument-hint: "[plan-slug|board-path] [--audit]"
---

# bosun status

Arguments: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`.

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, may); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

1. **Board.** The argument, else `TB latest`. If there is none, say there's no bosun plan in this repository and suggest `/bosun:plan` or `/bosun:manager`.
2. **Gather.** `TB status <board>`, `TB activity <board> --tail 10`, `git branch --show-current`, `git worktree list`.
3. **Show a compact dashboard**: the progress line; for an OpenSpec plan, the change and its tasks.md progress (if `TB status` reports drift, suggest `TB sync <board>`); tasks in flight (task, agent, elapsed time); blocked or failed tasks with their last note; the next ready tasks; notable recent events. Don't dump raw JSON.
4. **Audit** when `--audit` is given, or when something looks off (a task in flight much longer than the others, repeated failures, `STUCK`, worktrees with no matching in-flight task): spawn `bosun:monitor` with the board's absolute path, then show its health verdict and recommended actions.
5. **Don't change anything.** If the user wants to act on a recommendation, suggest the command (`/bosun:build <plan> --resume`, or the specific TB or git step) or do it once they say so.
