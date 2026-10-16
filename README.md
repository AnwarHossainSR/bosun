# bosun: your AI dev crew for Claude Code

[![CI](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml/badge.svg)](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

On a ship, the bosun is the officer who runs the deck crew. bosun is a Claude Code plugin that runs a crew of agents for your day-to-day programming. It gives you:

- a **manager**: one command that takes any goal and runs the right workflow;
- **spec-driven planning**: plans are [OpenSpec](https://github.com/Fission-AI/OpenSpec)-format changes (proposal, requirements with testable scenarios, design, tasks.md), and every task is traced to the requirements it implements;
- **10 specialist agents**: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor;
- **workflows**: plan, build, status, archive, investigate, review, review a PR, security audit, commit, ship;
- a **deterministic task board** (a small Python CLI) that schedules dozens of tasks across parallel agents by dependency and file ownership, and keeps the spec's tasks.md in step;
- **terse output** ("caveman" style) for agent reports and status updates, to spend fewer tokens on prose;
- **safety hooks** that apply only to bosun's own agents.

It's generic: nothing is tied to a language or framework. Project specifics (commands, conventions, protected paths) live in `.bosun/config.json`.

```
/bosun:manager "<any goal>"
   │
   ├─ plan ........ scouts ║ → architect → OpenSpec change (proposal, specs, design, tasks.md) + tasks.json
   │                 → spec-check + openspec validate → critique (architect ║ security) → you approve
   ├─ build ....... pool of N implementers, each in its own git worktree, each brief quoting its requirements
   │                 every task: code-reviewer (correctness ║ spec) ║ security-reviewer → verifier (if doubtful)
   │                 → merge + tick tasks.md → checks · monitor every ~10 tasks · board on disk, resumable
   ├─ archive ..... (only when you run it) openspec archive → requirements merged into openspec/specs/
   ├─ investigate . investigators on competing hypotheses ║ → verifier → report (+ test-first fix)
   ├─ review / review-pr / security-audit ... lens reviewers ║ → verifier → one ranked report
   └─ commit → ship (only when you run it) → pull request
                                                         ║ = runs in parallel
```

## Requirements

- **Claude Code with plugin support.** Built against, validated with and installed on Claude Code **2.1.301**. It uses plugin skills and agents, agent `model`/`effort` frontmatter, per-call worktree isolation, `SubagentStart`/`SubagentStop` hooks and the `worktree.baseRef` setting. I haven't tested older versions; they may ignore some of these.
- **git**, for worktree isolation. Without git, bosun runs in shared mode.
- **Python 3.10+** (CI tests 3.10 and 3.13) as `python3` on PATH, for the task board and the hooks. Without it the hooks show a non-blocking "hook error" notice and the skills fall back to editing `tasks.json` by hand.
- **GitHub CLI (`gh`)**, logged in, for `review-pr` and `ship` only.
- **OpenSpec CLI (optional)**: `npm install -g @fission-ai/openspec`. Planning and building work without it (bosun's own `spec-check` validates the change); with it, bosun also runs `openspec validate --strict`, and `/bosun:archive` needs it. Tested with OpenSpec **1.14.2**. Note: the OpenSpec CLI sends anonymous usage statistics unless you set `OPENSPEC_TELEMETRY=0` (or `DO_NOT_TRACK=1`); bosun's skills set `OPENSPEC_TELEMETRY=0` on the commands they run.
- Tested on Linux. macOS should behave the same. Windows is untested (see Limitations).

## Install

Pick one.

**A. From this folder (local marketplace).** Edits to the folder apply on the next session.
```bash
claude plugin marketplace add /path/to/bosun
claude plugin install bosun@bosun-marketplace
```
Inside a session, `/plugin marketplace add /path/to/bosun` does the same as the first command, and `/plugin install bosun@bosun-marketplace` opens the plugin panel where you install it.

**B. From GitHub** (works with a private repository as long as your local git can clone it):
```bash
claude plugin marketplace add AnwarHossainSR/bosun
claude plugin install bosun@bosun-marketplace
```

**C. For one project, shared with your team.** Run inside the project:
```bash
claude plugin marketplace add AnwarHossainSR/bosun --scope project
claude plugin install bosun@bosun-marketplace --scope project
```
This writes `extraKnownMarketplaces` and `enabledPlugins` to the project's `.claude/settings.json`; commit that file. Teammates get bosun after they accept the folder's trust prompt: the marketplace lists the plugin by a relative path, and the [Claude Code plugin docs](https://code.claude.com/docs/en/plugins/install.md) say such a plugin loads from the marketplace copy without a separate install. I haven't tried that with a second account. To follow a specific branch or tag, add it after `#`, for example `AnwarHossainSR/bosun#main`.

**D. Claude Code on the web (cloud sessions).** Cloud sessions don't load plugins installed on your own machine or turned on in the repository's `.claude/settings.json` (documented in the same docs). Install bosun inside the cloud container instead, by adding these lines to the environment's setup script (the environment menu in the session's title bar, then Edit, then Setup script), which runs when each new session starts:
```bash
claude plugin marketplace add AnwarHossainSR/bosun
claude plugin install bosun@bosun-marketplace
```
Both commands are safe to repeat: a second run reports "already installed" and exits 0. I haven't tested them through a setup script; in a cloud session, installing bosun this way inside the container did make its skills and agents available.

**E. Try it for one session without installing:**
```bash
claude --plugin-dir /path/to/bosun/plugins/bosun
```

Check it loaded: `claude plugin details bosun` should list Skills (12), Agents (10), Hooks (3).

## First run in a project

```text
/bosun:setup                      detect commands, write .bosun/config.json, keep .bosun/ out of git,
                                    and set worktree.baseRef = "head" (required for parallel builds; see below)
(start a new session if setup changed worktree.baseRef)
/bosun:plan a team task tracker with workspaces, kanban board and email notifications
                                  writes openspec/changes/<id>/ + the task board; you review and approve
                                  (or plan from an issue: /bosun:plan #123, or the issue URL)
/bosun:build                      runs the approved plan with parallel agents
/bosun:status --audit             any time, from the same session
/bosun:review                     final multi-lens review
/bosun:archive                    merge the finished change into openspec/specs/ (needs the OpenSpec CLI)
/bosun:commit
/bosun:ship                       push and open the PR (asks first)
```

Or hand anything to the manager and let it route:
```text
/bosun:manager migrate every API handler under src/handlers from callbacks to async/await
/bosun:manager why does checkout fail for some EU users since Tuesday?
/bosun:manager add tests to every module in packages/core that has none
```

## Commands

| Command | What it does |
|---|---|
| `/bosun:manager <goal>` | Triage any goal: picks plan/build, investigate, review, audit, an ad-hoc crew, or a single agent for small changes. |
| `/bosun:plan <idea>` | Clarifying questions, parallel scouts, the architect writes an OpenSpec change (proposal, specs with scenarios, design, tasks.md) and the task board, validation, architecture and security critique, your approval. `--classic` writes `PLAN.md` instead; naming an existing change only adds the board; `#123` or an issue URL plans from a GitHub issue and links it in the proposal and the PR. |
| `/bosun:build [plan]` | Executes a board: rolling pool of N agents in worktrees, review, spec and security gates, merge, tasks.md ticks, checks, monitor, resume (`--resume`), `--parallel`, `--review task\|batch\|final`, `--dry-run`. |
| `/bosun:archive [id]` | Checks every task is done and the change validates, runs `openspec archive`, re-validates the main specs, commits after you confirm. Only runs when you type it. |
| `/bosun:status [--audit]` | Dashboard: progress, in flight, blocked, next, recent agent activity; `--audit` adds the monitor agent's health check. |
| `/bosun:investigate <symptom>` | Frame, reproduce, 2-5 hypotheses, one investigator per hypothesis in parallel, verifier, written report; `--fix` fixes test-first. |
| `/bosun:review [target]` | Lens reviewers in parallel (correctness, spec, tests, security, design, performance, accessibility, api-compat), verified, de-duplicated report; `--fix`. |
| `/bosun:review-pr <n\|url>` | Same panel on a GitHub PR, checked out in a separate worktree; posts only after you approve the text. |
| `/bosun:security-audit [--full]` | Attack-surface map, installed scanners, security reviewers per area, verified findings, report; `--fix`. |
| `/bosun:commit` | Splits changes into logical commits, follows your convention, checks for secrets and leftovers, runs hooks, commits after you confirm. |
| `/bosun:ship` | Gate (lint, types, tests, build, quick review), push, PR from your template. Only runs when you type it. |
| `/bosun:setup` | One-time project setup (only runs when you type it). |

The agents can also be used directly, for example "use the bosun:security-reviewer agent on src/auth".

## Agents

| Agent | Role | Writes | Model / effort |
|---|---|---|---|
| `architect` | OpenSpec change (or PLAN.md) + task board; plan critique and revision | plan and spec files | inherit / high |
| `scout` | Read-only codebase map, research spikes | nothing | sonnet / medium |
| `implementer` | One task end to end: tests first, code, checks, commit on its branch | code | inherit |
| `test-engineer` | Unit, integration and e2e tests, flakiness checks | tests | inherit |
| `docs-writer` | README, docs, CHANGELOG, ADRs; runs what it documents | docs | sonnet / medium |
| `code-reviewer` | Diff review through one lens, evidence-backed findings | nothing | inherit / high |
| `security-reviewer` | Diff review, area audit, or threat model | nothing | inherit / high |
| `verifier` | CONFIRMED / REFUTED / UNCERTAIN per claim, with evidence | nothing | inherit / high |
| `investigator` | Tests one bug hypothesis with experiments | scratch only | inherit / high |
| `monitor` | Build health: stalls, failures, orphans, drift | nothing | haiku |

Every agent ends with a `# BOSUN-RESULT` YAML block (status, summary, evidence) that the manager parses. `inherit` means the model of your session.

## How a 40-task build runs

[examples/taskflow-40](examples/taskflow-40) is a 40-task example plan (a team task tracker). The board tool's view of it:

```text
$ python3 plugins/bosun/scripts/taskboard.py waves examples/taskflow-40/tasks.json --parallel 5
40 task(s) in 14 wave(s) at parallel 5; widest wave 5; critical path 29 size-units
  wave  1: T01 Scaffold monorepo, tooling, CI and in… | T02 Spike: choose the session strategy (s…
  wave  2: T04 API skeleton: config, error handling,… | T03 Shared domain schemas and types | T05 Web skeleton…
  ...
```

1. **Scheduling.** `taskboard.py next` returns tasks whose dependencies are done and whose owned files don't overlap anything in flight, longest critical path first. Overlap checks are conservative: a false conflict costs parallelism, never correctness.
2. **Rolling pool.** The manager keeps N agents busy (`--parallel`, default 4). Each code task runs in its own git worktree on its own branch. When an agent finishes, its gate starts immediately and the next ready task takes the free slot. There's no waiting for a whole wave.
3. **Gate per task.** A code-reviewer (correctness; spec for tasks with requirements; tests for high-risk tasks) and a security-reviewer for sensitive tasks run in parallel. Doubtful blocking findings go to the verifier. Fix rounds go back to the same implementer. Then `git merge --no-ff --no-commit`, fast checks on the merged tree, and only then the commit (which also carries the tasks.md tick). The full suite runs every ~5 merges; a merge that turns it red is undone with `git revert`, never a reset.
4. **Monitoring.**
   - Claude Code notifies the manager as each background agent finishes.
   - The hooks append every bosun agent's start and stop (with its result status) to `.bosun/activity.jsonl`.
   - The **monitor agent** runs every ~10 tasks and after repeated failures.
   - `/bosun:status --audit` works whenever you ask.
   The monitor is periodic, not a live daemon. Subagents can't keep watching in the background without burning tokens.
5. **Resume.** All state is in `tasks.json`. After an interruption, `/bosun:build --resume` gates surviving branches and resets the rest.
6. **Finish.** Full checks, a final multi-lens review of the whole range, docs, and `SUMMARY.md`. Pushing is left to `/bosun:ship`.

### Required setting for worktree builds

By default Claude Code creates agent worktrees from your repository's **default branch**, so task T07 wouldn't see T03's merged work. bosun needs worktrees created from your current HEAD. Add this to `.claude/settings.local.json`:

```json
{ "worktree": { "baseRef": "head" } }
```

`/bosun:setup` offers to add it, and `/bosun:build` checks it. Without it, build runs in shared mode: all agents in one checkout with strict file ownership, and the manager commits per task.

## Spec-driven plans (OpenSpec format)

`/bosun:plan` writes the plan as an [OpenSpec](https://github.com/Fission-AI/OpenSpec) change, so the "what" is agreed before any code exists and every task can be traced back to it:

```text
openspec/
  config.yaml                          schema: spec-driven (created if missing)
  specs/<capability>/spec.md           current behavior; changes only when a change is archived
  changes/<change-id>/
    .openspec.yaml                     schema and creation date
    proposal.md                        why, what changes, capabilities, impact
    specs/<capability>/spec.md         delta: ADDED / MODIFIED / REMOVED / RENAMED requirements
    design.md                          context, decisions, risks, migration plan
    tasks.md                           "- [ ] 1.1 ..." checklist, ticked by the build
.bosun/plans/<change-id>/tasks.json    the board: same task ids, plus deps, file ownership, agents
```

Each requirement states what the system SHALL do, and its scenarios become tests:

```markdown
### Requirement: Todo items are private
The system SHALL NOT reveal, change or delete a todo item for anyone but its owner, and SHALL answer such requests as if the item did not exist.

#### Scenario: Another user's item
- **WHEN** user A reads, updates or deletes an item owned by user B
- **THEN** the system returns 404 and the item is unchanged
```

How bosun uses it:
- **Traceability.** Each board task lists the requirements it implements in `spec_refs` (`"todo-items#Todo items are private"`). `taskboard.py spec-check` fails when an ADDED or MODIFIED requirement has no task, a reference doesn't resolve, or tasks.md and the board disagree. It also catches common format mistakes: no SHALL/MUST, a scenario written with three `#`, prose that archiving would drop, a MODIFIED block that loses scenarios, deltas that `openspec archive` would refuse.
- **Briefs quote the contract.** `taskboard.py brief` pastes the task's requirement blocks verbatim into the implementer's prompt. Implementers write one test per scenario, and a `spec` review lens checks every scenario against the code and the tests.
- **Only the architect edits the spec.** The guard blocks other bosun agents from changing OpenSpec files; they report disagreements as `spec_gaps`.
- **tasks.md stays true.** When the manager marks a task done, `taskboard.py set` ticks its line, inside the task's merge commit; reverting the merge unticks it. Follow-up tasks added during a build get a tasks.md line too.
- **Archive.** `/bosun:archive` checks that every task is ticked (`openspec archive --yes` itself doesn't stop on unticked tasks), then lets the OpenSpec CLI merge the deltas into `openspec/specs/`.

Already have an OpenSpec change, written by hand or with OpenSpec's own commands? `/bosun:plan <change-id>` only adds the board. Prefer a plain plan? Use `/bosun:plan --classic ...` or set `"planning": {"format": "plan"}`.

bosun is not affiliated with OpenSpec. It writes the OpenSpec 1.x file formats, checked against the 1.14.2 CLI and its source; if a later OpenSpec release changes them, `openspec validate` is the authority. [examples/openspec-todo-api](examples/openspec-todo-api) is a small complete example that passes both `spec-check` and `openspec validate --strict`.

## Terse output ("caveman" style)

Agent reports flow into the manager's context, and the manager's updates flow to you. With `output_style: "caveman"` (the default), every bosun agent is told at start (by the SubagentStart hook), and every bosun skill is told in its instructions, to write prose as short fragments without filler, pleasantries or hedging words. Code, commands, paths, error text and numbers stay exact. Commit messages, PR text, docs and the specs are written normally. Security warnings, destructive steps, ordered instructions and questions get full sentences, and uncertainty labels (unverified, not run, assumption) are always kept.

| `output_style` | Prose |
|---|---|
| `caveman` (default) | fragments; no articles, filler or pleasantries |
| `caveman-lite` | short complete sentences; no filler |
| `caveman-ultra` | telegraphic; common abbreviations |
| `normal` | unchanged |

`BOSUN_OUTPUT_STYLE=normal` (or another level) overrides the config for a session. The style text adds roughly 150-200 tokens per agent start (estimated from its length).

How much it saves, measured on a small sample: agents wrote four typical bosun messages (an implementer result, review findings, an investigation report, a progress update) in normal prose; other agents rewrote each one at every level with these rules, and separate agents checked each rewrite for lost facts.

| `output_style` | Fewer words in the prose | Fewer words in the whole message (with the result block) |
|---|---|---|
| `caveman-lite` | about 11% | about 8% |
| `caveman` | about 25% | about 20% |
| `caveman-ultra` | about 27% | about 21% |

No real facts were lost; the checkers flagged only minor wording losses, such as a dropped count that the listed ids still show. Treat the numbers as rough: four messages, one rewrite each, and words are only a proxy for tokens. They also cover only what agents write. Most tokens in agent work are usually input (instructions, files, tool output), which this style doesn't change, so the saving on a whole session is much smaller. It works independently of any caveman-style skill you may use in your own sessions.

## Safety model

The hooks in `hooks/hooks.json` act only when the tool call comes from a bosun agent (`agent_type` starting with `bosun:`). Your own session and other agents are never touched.

| Blocked for bosun agents | Why |
|---|---|
| `git push`, `git pull`, `git stash`, worktree add/remove, deleting or renaming branches, tags, remote or config changes, history rewriting, `commit --no-verify` | shared state; the manager or you decide |
| In the shared checkout: commit, add, reset, checkout or restore of everything, switch, merge, rebase, clean | would capture or destroy other agents' work (allowed inside an agent's own worktree) |
| Recursive `rm` of `/`, `~`, `.`, `..`, `.git` and similar | catastrophic deletes |
| `gh` write actions (PR create/merge/comment/review, issues, releases, API POST/PATCH/DELETE, GraphQL mutations, `gh auth token`) | acting on GitHub as you |
| Publishing and deploying (`npm publish`, `cargo publish`, `docker push`, `vercel --prod`, `wrangler deploy`, `npm run deploy` and similar), infrastructure changes (terraform apply, kubectl apply/delete, helm upgrade and similar), `sudo`, `curl … \| sh` | outside the machine, or unreviewed code |
| Edits to `.git/`, `.claude/settings*.json`, `.bosun/` (except `.bosun/scratch/`; the architect may write plans) and your `protected_paths` | integrity, permission escalation, the board |
| Edits to OpenSpec files (`openspec/changes/`, `openspec/specs/`, `openspec/config.yaml`), except by the architect | the spec is the agreed contract; the manager ticks tasks.md |

Switches: `BOSUN_GUARD=0` turns the guard off. `BOSUN_ENFORCE_RESULT=1` makes a bosun agent continue once if it stops without a result block (off by default, because it could also fire when you stop an agent yourself). `BOSUN_OUTPUT_STYLE` overrides `output_style`.

The guard is a safety net against accidents, **not a security boundary**. It parses command text, so it can't see what a script does internally, and a determined agent could get around it. Keep your normal Claude Code permission settings.

Other built-in brakes: `ship`, `setup` and `archive` only run when you type them; `review-pr` posts only text you approved; commit never pushes; no agent installs tools or touches remote services on its own.

## Configuration

`.bosun/config.json` (written by `/bosun:setup`; template in `plugins/bosun/templates/config.json`):

| Key | Meaning | Default |
|---|---|---|
| `commands.install/test/test_one/lint/typecheck/build/format/e2e` | exact commands; injected into every bosun agent at start | detected |
| `planning.format` | `openspec` (OpenSpec change + board) or `plan` (PLAN.md + board) | openspec |
| `planning.openspec_dir` | where the OpenSpec directory lives | openspec |
| `output_style` | `caveman`, `caveman-lite`, `caveman-ultra` or `normal` (see Terse output) | caveman |
| `build.max_parallel` | agents in flight | 4 |
| `build.isolation` | `worktree` or `shared` | worktree |
| `build.review` | `task` (gate every task), `batch` (gate every N merges), `final` (final review only) | task |
| `build.security_review` | `always`, `sensitive`, `final`, `off` | sensitive |
| `build.max_attempts` | dispatches per task before it's marked blocked | 2 |
| `build.merge` | `merge` (`--no-ff`) or `squash` | merge |
| `conventions.commit_style`, `conventions.notes` | passed to every agent | detected |
| `protected_paths` | globs bosun agents may never edit (e.g. `.github/workflows/**`) | [] |

Also useful:
- **`.worktreeinclude`** (gitignore syntax) makes Claude Code copy gitignored files such as `.env` into each new worktree.
- **`CLAUDE.md`**: subagents load it automatically, so put team conventions there.
- **`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`**: Claude Code's limit on simultaneous subagents (documented default 20).

## Customize

- **Models and effort**: edit the frontmatter in `plugins/bosun/agents/*.md` (`model: inherit|sonnet|opus|haiku|fable|<full model id>`, `effort: low|medium|high|xhigh|max`). For example, run implementers on `sonnet` to cut cost.
- **Your own agents**: put them in `.claude/agents/` or another plugin and name them in a task's `agent` field. The board accepts any agent name.
- **Custom review lens**: `/bosun:review --lenses correctness,i18n` and describe the i18n checklist in the request.
- **Planning rules and board schema**: `python3 plugins/bosun/scripts/taskboard.py schema`.
- **Very large fan-outs** (hundreds of uniform items): if your Claude Code offers dynamic workflows, you can ask the manager to "use a workflow" with the same agents and gates.

## Cost, honestly

Each agent has its own context window, so multi-agent work uses **many more tokens** than one session. A 40-task build means at least 40 implementer runs, 40-80 reviewer runs, plus planning, verification and monitoring. I can't give you a reliable number. Run a small plan first and watch your usage.

Levers: lower `max_parallel`; `review: batch`; implementers on `sonnet`; `--no-critique` for small plans; keep `output_style` terse; `/bosun:manager` already skips the crew for small changes.

The plugin also adds about **2.5k tokens to every session** for the skill and agent listings (`claude plugin details bosun` shows this). Disable it in projects where you don't use it (`/plugin`).

## What has been verified, and what hasn't

Verified while building this:
- the unit tests in `tests/` pass (task board scheduling, validation, locking under concurrent writes; OpenSpec parsing, spec-check, tasks.md ticking and sync; guard rules including false-positive cases; hook events and output styles);
- `claude plugin validate --strict` passes for the plugin and the marketplace;
- installing from the local marketplace loads 12 skills, 10 agents and 3 hooks on Claude Code 2.1.301;
- the git commands the build skill prescribes were run in a scratch repository (worktrees, `--no-ff` merges, `--no-commit` merge plus tasks.md tick in one commit, merge revert unticking it, aborting a squash merge, path-limited commits for shared mode, cleanup after squash);
- with OpenSpec 1.14.2: the example change passes `openspec validate --strict`; an archive round trip (all tasks ticked, `openspec archive`, `openspec validate --specs --strict`) works; and `spec-check` was compared with `openspec validate` and `openspec archive` on deliberately broken changes.

**Not verified: a full live multi-agent build**, and the terse style's savings on real builds (only the small sample above was measured). A build runs real Claude sessions on your account, so I didn't start one. Try it first on a small throwaway repository. LLM agents follow instructions imperfectly; the gates and the verifier reduce mistakes but don't remove them. Review the merged result before you ship.

Known limitations:
- Worktree mode needs `worktree.baseRef: "head"`. Each worktree installs its own dependencies, which is slow for large JS projects.
- Inline PR review comments: the GitHub payload format couldn't be checked here, so the default is one review comment, and the skill tells Claude to check GitHub's docs before posting inline comments.
- Windows: untested. `python3` may be called `python`, and PowerShell tool calls aren't inspected by the guard.
- Agent teams (experimental in Claude Code) are optional. Builds are designed for ordinary subagents.

## Repository layout

```text
.claude-plugin/marketplace.json        marketplace (lists the plugin)
plugins/bosun/
  .claude-plugin/plugin.json           plugin manifest
  skills/<name>/SKILL.md               12 workflows (build/reference/execution.md holds edge cases)
  agents/<name>.md                     10 agents
  hooks/hooks.json + bosun_hooks.py    guard, activity log, context and output-style injection
  scripts/taskboard.py                 task board CLI with OpenSpec checks (stdlib only)
  templates/config.json                project config template
examples/taskflow-40/                  40-task example plan (classic PLAN.md + tasks.json)
examples/openspec-todo-api/            OpenSpec example: openspec/ change + .bosun/ board
tests/                                 unit tests
LICENSE                                MIT
```

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate --strict ./plugins/bosun && claude plugin validate --strict .
claude plugin details bosun      # after installing from the local marketplace
(cd examples/openspec-todo-api && OPENSPEC_TELEMETRY=0 openspec validate add-todo-api --strict --no-interactive)
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md) for reporting vulnerabilities privately.

## License

[MIT](LICENSE)
