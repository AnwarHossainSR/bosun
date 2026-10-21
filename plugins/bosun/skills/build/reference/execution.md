# bosun build: execution details

Read only the section you need.

## Worktree mode mechanics

- An agent spawned with `isolation: "worktree"` gets a private git worktree on a new branch (by default under `.claude/worktrees/`). With `worktree.baseRef` set to `"head"`, it starts from the main checkout's current HEAD: the work branch with everything merged so far. Worktrees contain only committed state, so commit each merge before dispatching the tasks that depend on it.
- The agent reports its `branch` and `worktree` in its result; prefer those over guesses. `git worktree list` shows all worktrees.
- A worktree whose agent made no changes is removed automatically. Worktrees with changes stay until `git worktree remove <path>` (`--force` only for throwaway investigator worktrees). A worktree git reports as locked may still have a running agent: check before you unlock anything.
- Dependencies (node_modules, virtualenvs, build caches) are per worktree; implementers run the install command first. Gitignored files such as `.env` are present only if `.worktreeinclude` lists them.

## Shared mode

Use it when the repository isn't a git repository, when the user prefers it, or when the worktree base can't be set to `head`.

- Always pass `--strict-files` to `TB next`, so tasks without declared files run alone.
- Implementers edit the main checkout and never stage or commit; the bosun guard hook enforces this for bosun agents.
- Reviewers get `git diff -- <task files>` plus the task's untracked files (`git status --porcelain -- <paths>`).
- Gate passed and fast checks green: record the task first (`TB set <board> <ID> --status done --summary "..."`; for an OpenSpec plan this ticks tasks.md), then commit only that task's files plus tasks.md (leave tasks.md out when the OpenSpec directory is local, that is git-ignored): `git add -- <files> [<tasks.md>]`, then `git commit -m "bosun(<ID>): <title>" -- <files> [<tasks.md>]`, then `TB set <board> <ID> --commit <sha>`.
- Tests run by one agent can see other agents' half-finished edits. Treat red results during a busy wave with suspicion: re-run the checks once the wave settles before failing a task.

## Review policies

- `task` (default): gate every code task before merging it, as in section 2 of the skill.
- `batch`: merge after the implementer's own checks pass and your spot-check. Every N merges (N = max_parallel), run one gate on the combined diff of those merges. Findings become fix tasks.
- `final`: no per-task gate, only the final review. Fastest and riskiest; suggest it only for low-risk mechanical work.

Security policy: `always`, `sensitive` (default), `final`, or `off`.

## Conflicts

When `git merge` reports a conflict:

1. `git merge --abort`. The main checkout is back where it was.
2. Only lockfiles or generated files conflict: merge again and resolve them by regenerating (run the install or the generator), then run checks and commit the merge.
3. Small textual conflicts with an obvious union (imports, lists, registries): resolve them yourself, run the checks, commit the merge.
4. Anything else: spawn an implementer in a new worktree (it starts from the work branch) with: "Merge `<task_branch>` into your branch, resolve the conflicts preserving the intent of both sides (the task's brief: `<TB> brief <absolute board path> <ID>`), run the tests, commit." Merge that agent's branch instead, and delete the old task branch.

Never resolve a conflict by throwing away one side wholesale without understanding it.

## Resume

Agents from the earlier session are gone; `TB status <board>` and `git worktree list` show what survived. Decide during preflight step 4 and act only after the go-ahead in step 5.

**Each task's work**
- `review` task: the board fields `branch` and `worktree`. With commits: run its gate (skill, section 2, step 3) before dispatching new work.
- `in_progress` task: `branch` and `worktree` are written only at review, so they're missing or left over from an earlier attempt. Look in `git worktree list` for the worktree with commits named `<type>(<ID>): ...` or uncommitted changes in the task's files. A retry starts by merging the previous attempt's branch, so when several match, the latest attempt is the one whose branch contains the others (`git merge-base --is-ancestor <other_branch> <branch>`); the older ones are superseded. If you can't tell which worktree is the task's, don't guess: treat the task as having no work.
- `in_progress` with commits or uncommitted changes: the work may be unfinished.
  - Its worktree is itself mid-merge (`git -C <worktree> rev-parse -q --verify MERGE_HEAD` succeeds): don't stage or commit anything there (`git add` would mark conflicted files resolved, and git refuses a partial commit during a merge). List it in step 5 for the user, as it is. No retry until the user has decided.
  - Otherwise check each uncommitted path with `git -C <worktree> status --porcelain --untracked-files=all` (it names the files inside new directories). Commit only those in the task's files, with path-limited commands: `git -C <worktree> add -- <paths>`, then `git -C <worktree> commit -m "<type>(<ID>): <summary>" -- <paths>` (never `git add -A`: the worktree can hold stray files). List any other path in step 5 for the user to decide. Then retry the task with an implementer whose prompt starts with "First run `git merge <task_branch>`".
- No work: set the task back to pending (skill, preflight step 4).
- The work branch contains a merge for a task the board doesn't mark done, or marks done without a `commit` (the session stopped between committing and `TB set --commit`): set it done with that merge's sha.

**Unfinished merge in the main checkout** (`git rev-parse -q --verify MERGE_HEAD` succeeds, or after a squash the file at `git rev-parse --git-path SQUASH_MSG` exists). It usually means the session stopped between `git merge --no-commit` and `git commit`. The user may have started it instead, and a task match doesn't prove otherwise, so settle it only after the user's go-ahead, and before any other resume action. To propose an action:
- Find its task: `MERGE_HEAD` is the tip of the merged branch, and `SQUASH_MSG` lists the squashed commits (`<type>(<ID>): ...`). Compare them with the `branch` of each `review` task, and of each `done` task without a `commit` (the session stopped right after `TB set --status done`).
- Check that it holds nothing else: every path in `git diff --cached --name-only` is in `git diff --name-only HEAD...<task_branch>`, and `git diff --name-only` (unstaged changes) lists nothing but conflicted paths. In both lists the plan's tasks.md is allowed too: `TB set --status done` ticks it in the working tree without staging it.
- Conflicted paths (`git diff --name-only --diff-filter=U`) mean the session stopped while resolving a conflict. A half-done resolution can't be trusted, so propose undoing the merge.
- No matching task, or other changes: show what you found and leave the merge to the user, and don't dispatch tasks until it's settled (skill, preflight step 4).
- Otherwise, after the go-ahead, either undo it with `git merge --abort` (`git reset --merge` after a squash) and set the task back to `review`, so it is gated and merged again from the start, or, if it has no conflicts, run the integration check again and commit it (after `TB set <board> <ID> --status done`, if it isn't done yet).

**OpenSpec plans:** `TB status <board>` reports tasks.md drift; `TB sync <board>` repairs it, then commit tasks.md (not when the OpenSpec directory is local: git ignores it).

Recent agent activity: `TB activity <board> --tail 30`; agents' final messages: `.bosun/plans/<name>/results/`.

## Agent teams (optional)

If agent teams are enabled (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`), an Agent call with a `name` and without `isolation` starts a teammate instead of a subagent. Builds are designed for subagents, so leave `name` off report tasks when teams are enabled.

## Very large fan-outs

For hundreds of uniform items (for example a 300-file migration), one conversation shouldn't coordinate every agent. If the user's Claude Code offers dynamic workflows, ask whether to "use a workflow" with the same agents and the same gates.
