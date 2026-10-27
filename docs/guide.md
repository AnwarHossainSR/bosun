# bosun guide

The details behind the [README](../README.md): every command, how plans and builds run, the agents, token use, configuration and safety.

- [Commands](#commands)
- [Spec-driven plans](#spec-driven-plans)
- [How a build runs](#how-a-build-runs)
- [Reviews](#reviews)
- [The crew](#the-crew)
- [Token use](#token-use)
- [Configuration](#configuration)
- [Safety](#safety)
- [More install options](#more-install-options)
- [Status](#status)

## Commands

| Command | What it does |
|---|---|
| `/bosun:manager <goal>` | Routes any goal to the lightest workflow, from a single agent to a full crew. |
| `/bosun:propose <idea \| #issue>` (or `/bosun:plan`) | Clarifying questions, an OpenSpec change and a task board, then your approval. One architect writes it, as OpenSpec's propose does; `--crew` adds scouts and a critique round with a threat model, `--critique` just the critique, and `--solo` or `--crew` carries over to the build. `--classic` writes a PLAN.md instead. |
| `/bosun:apply [plan]` (or `/bosun:build`) | Builds the board solo or with parallel agents in worktrees, with review-gated merges and resume (`--solo`, `--crew`, `--resume`, `--parallel N`, `--only 1.1,2.3`, `--dry-run`). Shows progress as OpenSpec's apply does (`✓ 1.2 · 3/7`). An OpenSpec change without a board gets one first. |
| `/bosun:status [--audit]` | Progress, work in flight, blocked tasks and what's next; `--audit` adds a health check. Runs only when you type it. |
| `/bosun:review [target]` | Lens review of the branch, staged or working changes, a range or a commit; `--fix` applies confirmed fixes. |
| `/bosun:review-pr <n \| url>` | The same review on a GitHub pull request, in a separate worktree. Posts only text you approve. |
| `/bosun:investigate <symptom>` | Competing hypotheses tested in parallel, a verified root cause and a report; `--fix` fixes it test-first. |
| `/bosun:security-audit [--full]` | Attack-surface map, your installed scanners, reviewers per area and verified findings. |
| `/bosun:commit` | Logical commits in your convention, checked for secrets and leftovers. Never pushes. |
| `/bosun:ship` | Final checks, push and a pull request from your template. Asks first; runs only when you type it. |
| `/bosun:archive [id]` | Merges a finished OpenSpec change into the main specs. Runs only when you type it. |
| `/bosun:setup` | One-time project setup. Runs only when you type it. |

`propose`, `apply` and `archive` are OpenSpec's own names for these steps. You can also call an agent directly: "use the bosun:security-reviewer agent on src/auth".

## Spec-driven plans

```text
openspec/
  specs/<capability>/spec.md          current behavior; changes only when a change is archived
  changes/<change-id>/
    proposal.md                       why, what changes, impact
    specs/<capability>/spec.md        ADDED / MODIFIED / REMOVED requirements with scenarios
    design.md                         decisions, risks, migration plan
    tasks.md                          "- [ ] 1.1 ..." checklist, ticked as tasks merge
.bosun/plans/<change-id>/tasks.json   the board: same task ids, plus deps, file ownership, agents
```

- Each requirement says what the system SHALL do, and each of its scenarios becomes a test.
- `spec-check` catches requirements without tasks, broken references and format mistakes before anything is built.
- Only the architect edits the spec; other agents report disagreements as `spec_gaps`.
- `/bosun:archive` merges the finished change into the main specs with the [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec).

Plans are lean by default, security-sensitive ones included: the architect alone reads the code it needs, with no scouts and no critique round, and writes the failure and authorization scenarios itself. Only large work (a new product, or several subsystems at once) gets scouts. A critique and threat model run only when you ask (`--critique`, `--crew`, or when the plan is shown to you); either way, the build's security review checks security-sensitive tasks.

**Already using OpenSpec for your own work?** Give bosun its own git-ignored folder, so your specs stay yours. `/bosun:setup` offers this when it finds an `openspec/` folder that isn't bosun's:

```json
{ "planning": { "format": "openspec", "openspec_dir": ".bosun/openspec" }, "protected_paths": ["openspec/**"] }
```

[examples/openspec-todo-api](../examples/openspec-todo-api) is a complete example that passes `openspec validate --strict`.

## How a build runs

The task board picks the route from the plan's size and agents; `--crew` forces the crew, and `--solo` a solo run unless a task needs its own agent.

**Solo,** for plans of up to 8 tasks and 16 size-units (S 1, M 2, L 3) whose tasks are all code tasks for the implementer, test-engineer or docs-writer, in worktree mode. One implementer works through the tasks in tasks.md order in one git worktree, tests first, with a commit per task. Then the whole run gets one review (correctness, tests and spec, plus security when it matters), one `--no-ff` merge and the full checks. A run that stops early continues from its commits.

**Crew,** for bigger plans, plans with a task for another agent, and shared mode:

1. **Schedule.** The task board starts tasks whose dependencies are done and whose files don't overlap work in flight, critical path first, keeping up to `--parallel` agents busy (default 4).
2. **Build.** Each implementer works in its own git worktree and reads its brief, which quotes the requirements it implements. Tests come first.
3. **Gate.** With the default `build.review: task`, each task gets a code review (correctness, plus spec and tests where they apply) and a security review when it touches sensitive code, then a `--no-ff` merge with fast checks on the merged tree. The full suite runs every few merges; a merge that turns it red is reverted, never reset.

Either way the board lives on disk, so `/bosun:apply --resume` continues after any interruption. A build finishes with full checks, a final review of the whole range (a solo run's single review already was one), docs and a `SUMMARY.md`. Pushing waits for `/bosun:ship`.

Worktree builds need `{ "worktree": { "baseRef": "head" } }` in `.claude/settings.local.json`, so each worktree starts from the merged work; `/bosun:setup` offers to add it.

## Reviews

- **Lenses in parallel.** Correctness always, plus spec, tests, security, design, performance, accessibility or API compatibility when the change calls for them. One reviewer covers every lens for a diff of up to about 600 changed lines; a larger diff gets a reviewer per lens.
- **Verified.** A verifier re-checks every critical and high finding before you see it.
- **Readable.** Findings are ranked 🔴 critical, 🟠 high, 🟡 medium, 🔵 low and ⚪ nit, under a verdict and a count table. Each one gives its `path:line`, the problem, its impact and a fix, with ready-to-apply code when the fix only changes those lines. ✅ means the verifier confirmed it, ❔ that it was uncertain.
- **On GitHub,** `/bosun:review-pr` links each location to the line at the PR's head commit and can post each finding on its line. A fix for exactly the commented lines becomes a GitHub suggestion the author can commit in one click.
- **Lean diffs.** Lockfiles and files marked `linguist-generated` stay out of reviewers' diffs; a changed lockfile goes to the security reviewer alone. Reviewers never install dependencies, and `/bosun:review-pr` asks before running any of a PR's code.

## The crew

| Agent | Does | Writes |
|---|---|---|
| `architect` | specs, plans, plan critique | plan and spec files |
| `scout` | maps code, answers research spikes | nothing |
| `implementer` | a task end to end, or a small plan's tasks in order: tests, code, checks, commit | code |
| `test-engineer` | unit, integration and e2e tests, flakiness checks | tests |
| `docs-writer` | docs that match the code | docs |
| `code-reviewer` | diff review through one or more lenses | nothing |
| `security-reviewer` | diff review, audits, threat models | nothing |
| `verifier` | confirms or refutes claims with evidence | nothing |
| `investigator` | tests one bug hypothesis | scratch files only |
| `monitor` | build health checks | nothing |

Every agent ends with a short `# BOSUN-RESULT` block that the manager acts on.

## Token use

**Models.** The work that needs judgment runs on the latest Opus (`model: opus`, effort `high`): architect, implementer, test-engineer, code-reviewer, security-reviewer, verifier and investigator. The rest runs on Haiku: scout, docs-writer and monitor, plus `/bosun:status` and `/bosun:archive`, which switch the session to Haiku for their turn. That works on Claude Code 2.1.259 and later; in auto mode, Claude Code keeps the session's model for a skill whose model doesn't support auto mode. Change an agent's model in its `plugins/bosun/agents/<name>.md`.

- **About 1k tokens per session** for the skill and agent listings (`claude plugin details bosun` shows the estimate). Turn bosun off in projects that don't use it with `/plugin`.
- **Only what a run needs.** Rarely used instructions (the crew route, review fixes, resume, the classic plan outline) load only when that path runs.
- **Right-sized work.** A lean plan has one architect and a solo build one implementer and one review. Reviews and investigations start no more agents than the change needs.
- **Results go to disk.** A hook saves each agent's report next to its plan; the manager reads the short result block and points later agents to the file instead of retyping it.
- **Quiet logs.** Long test, build and scanner output goes to a log, and agents read the last 40 lines unless something failed.
- **Terse prose.** Agent reports use a short "caveman" style. Code, commands, paths and quoted specs stay exact, and commits, PRs and docs stay normal prose. Set `output_style` to `normal` to turn it off.

**What each run cost.** Review, review-pr, security-audit, investigate, plan and build end with token lines read from Claude Code's own transcript files: this run and its agents, the whole session, and how much of the context window is left. Agents' output counts are a lower bound (their transcripts often keep only a reply's first count), and the window size is inferred from the model unless you set `CLAUDE_CODE_MAX_CONTEXT_TOKENS`. Plan limits aren't in those files; `/usage` shows them.

**Spending less.** Start bosun in a fresh session (`/clear`): the manager re-reads its whole context on every turn, and plan and build warn when it's over about 100k tokens. A lower effort level for the session cuts the manager's thinking. A crew build still does much more work than a single session: try `--solo` when the board allows it, lower `build.max_parallel`, or use `build.review: batch`.

## Configuration

`/bosun:setup` writes `.bosun/config.json` (template: [plugins/bosun/templates/config.json](../plugins/bosun/templates/config.json)):

| Key | Meaning | Default |
|---|---|---|
| `commands.*` | install, test, test_one, lint, typecheck, build, format, e2e; given to every bosun agent | detected |
| `planning.format` | `openspec` or `plan` (PLAN.md) | `openspec` |
| `planning.openspec_dir` | bosun's OpenSpec folder; `.bosun/openspec` keeps it local and out of git | `openspec` |
| `output_style` | `caveman`, `caveman-lite`, `caveman-ultra` or `normal` | `caveman` |
| `build.max_parallel` | agents in flight | 4 |
| `build.isolation` | `worktree` or `shared` | `worktree` |
| `build.review` | `task`, `batch` or `final` | `task` |
| `build.security_review` | `always`, `sensitive`, `final` or `off` | `sensitive` |
| `build.max_attempts` | tries per task before it's marked blocked | 2 |
| `build.merge` | `merge` (`--no-ff`) or `squash` | `merge` |
| `conventions.commit_style`, `conventions.notes` | passed to every agent | detected |
| `protected_paths` | globs bosun agents may never edit | `[]` |

Customize agents in `plugins/bosun/agents/*.md` (`model`, `effort`), name your own `.claude/agents/` in a task's `agent` field, or add a review lens on the fly: `/bosun:review --lenses correctness,i18n`.

## Safety

- The guard hook acts only on bosun's own agents (`agent_type` starting with `bosun:`). It blocks risky actions such as `git push`, `stash` and history rewriting, commits outside an agent's own worktree, writes to the task board (only the manager writes it), publishing and deploys, infrastructure changes, `gh` write actions, `sudo`, `curl … | sh`, catastrophic deletes, and edits to `.git/`, `.claude/settings*.json`, `.bosun/` (scratch files aside), OpenSpec files (except by the architect) and your `protected_paths`.
- `ship`, `setup` and `archive` run only when you type them; `review-pr` posts only text you approved; `commit` never pushes.
- Switches: `BOSUN_GUARD=0` turns the guard off; `BOSUN_ENFORCE_RESULT=1` makes an agent continue once if it stops without a result block; `BOSUN_OUTPUT_STYLE` overrides `output_style`.

The guard is a safety net against accidents, not a security boundary: it reads command text, not what scripts do. Keep your usual Claude Code permission settings. What bosun runs, writes and connects to is listed in the [plugin README](../plugins/bosun/README.md).

## More install options

- **Claude Code on the web:** run the marketplace and install commands in the environment's setup script; both are safe to run again.
- **Try it without installing:** `claude --plugin-dir /path/to/bosun/plugins/bosun`.
- **Teammates:** on a repository installed with `--scope project`, a teammate who doesn't see bosun runs the marketplace and install commands once.
- **Updating:** pass the scope you installed with (`--scope local` or `--scope project`); some Claude Code versions update only user scope otherwise.

## Status

bosun is young and moving fast. The unit tests (task board, OpenSpec checks, guard, hooks, token report), strict plugin validation, the git flows the build uses and OpenSpec round trips are verified. A full multi-agent build on a real project is the next milestone, so start with a small plan and review merged work before you ship it. Developed and tested on Linux; on Windows it needs `python3` on `PATH` for the hooks, task board and token report, and has had less testing.
