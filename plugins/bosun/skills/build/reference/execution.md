# bosun build: execution details

Read only the section you need.

## Worktree mode mechanics

- Spawning an agent with `isolation: "worktree"` gives it a private git worktree on a new branch (by default under `.claude/worktrees/`). With `worktree.baseRef` set to `"head"`, the worktree starts from the main checkout's current HEAD: the work branch with everything merged so far. Worktrees contain only committed state, so commit each merge before dispatching the tasks that depend on it.
- The agent reports its `branch` and `worktree` in its result. Prefer those over guesses; `git worktree list` shows all worktrees.
- A worktree whose agent made no changes is removed automatically. Worktrees with changes stay until you remove them with `git worktree remove <path>` (use `--force` only for throwaway investigator worktrees). If git reports the worktree as locked, its agent may still be running: check before you unlock anything.
- Dependencies (node_modules, virtualenvs, build caches) are per worktree; implementers run the install command first. Gitignored files such as `.env` are present only if `.worktreeinclude` lists them.

## Shared mode

Use it when the repository isn't a git repository, when the user prefers it, or when the worktree base can't be set to `head`.

- Always pass `--strict-files` to `TB next`, so tasks without declared files run alone.
- Implementers edit the main checkout and never stage or commit. The bosun guard hook enforces this for bosun agents.
- Reviewers get `git diff -- <task files>` plus the task's untracked files (`git status --porcelain -- <paths>`).
- When the gate passes and the fast checks are green, record the task first (`TB set <board> <ID> --status done --summary "..."`; for an OpenSpec plan this ticks tasks.md), then commit only that task's files plus tasks.md: `git add -- <files> [<tasks.md>]`, then `git commit -m "bosun(<ID>): <title>" -- <files> [<tasks.md>]`, then `TB set <board> <ID> --commit <sha>`.
- Tests run by one agent can see other agents' half-finished edits. Treat red results during a busy wave with suspicion: re-run the checks once the wave settles before failing a task.

## Review policies

- `task` (default): gate every code task before merging it, as in section 2 of the skill.
- `batch`: merge after the implementer's own checks pass and your spot-check. Every N merges (N = max_parallel), run one gate on the combined diff of those merges. Findings become fix tasks.
- `final`: no per-task gate, only the final review. Fastest and riskiest; suggest it only for low-risk mechanical work.

Security policy: `always`, `sensitive` (default), `final`, or `off`.

## Conflicts

When `git merge` reports a conflict:

1. `git merge --abort`. The main checkout is back to where it was.
2. Only lockfiles or generated files conflict: merge again and resolve them by regenerating (run the install or the generator), then run checks and commit the merge.
3. Small textual conflicts with an obvious union (imports, lists, registries): resolve them yourself, run the checks, commit the merge.
4. Anything else: spawn an implementer in a new worktree (it starts from the work branch) with: "Merge `<task_branch>` into your branch, resolve the conflicts preserving the intent of both sides (task brief below), run the tests, commit." Merge that agent's branch instead, and delete the old task branch.

Never resolve a conflict by throwing away one side wholesale without understanding it.

## Resume details

- `TB status <board>` and `git worktree list` show what survived the interruption. A task in `review` with a branch gets gated again. An `in_progress` task with commits on its branch is a partial result: spawn an implementer to finish it, starting with `git merge <task_branch>`. Both happen after the go-ahead (skill, preflight step 5).
- If the work branch contains a merge for a task the board doesn't mark done (the session stopped between committing and `TB set --commit`), mark it done with that merge's sha.
- A merge still in progress (`git rev-parse -q --verify MERGE_HEAD` succeeds, or `git status` shows staged squash changes) means the session stopped between `git merge --no-commit` and `git commit`. Run the integration check again, then either commit it (after `TB set <board> <ID> --status done`) or undo it with `git merge --abort` (`git reset --merge` after a squash) and set the task back to `review`.
- OpenSpec plans: `TB status <board>` reports tasks.md drift; `TB sync <board>` repairs it, then commit tasks.md.
- Recent agent activity: `TB activity <board> --tail 30`.

## Agent teams (optional)

If agent teams are enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), an Agent call with a `name` and without `isolation` starts a teammate instead of a subagent. Builds are designed for subagents, so leave `name` off report tasks when teams are enabled.

## Very large fan-outs

For hundreds of uniform items (for example a 300-file migration), one conversation shouldn't coordinate every agent. If the user's Claude Code offers dynamic workflows, ask whether to "use a workflow" with the same agents and the same gates.
