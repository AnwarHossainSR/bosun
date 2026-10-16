# bosun: your AI dev crew for Claude Code

[![CI](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml/badge.svg)](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

On a ship, the bosun is the officer who runs the deck crew. bosun is a Claude Code plugin that runs a crew of agents for your day-to-day programming. It gives you:

- a **manager**: one command that takes any goal and runs the right workflow;
- **10 specialist agents**: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor;
- **workflows**: plan, build, status, investigate, review, review a PR, security audit, commit, ship;
- a **deterministic task board** (a small Python CLI) that schedules dozens of tasks across parallel agents by dependency and file ownership;
- **safety hooks** that apply only to bosun's own agents.

It's generic: nothing is tied to a language or framework. Project specifics (commands, conventions, protected paths) live in `.bosun/config.json`.

```
/bosun:manager "<any goal>"
   │
   ├─ plan ........ scouts ║ → architect → critique (architect ║ security) → PLAN.md + tasks.json → you approve
   ├─ build ....... pool of N implementers, each in its own git worktree
   │                 every task: code-reviewer ║ security-reviewer → verifier (if doubtful) → merge → checks
   │                 monitor agent every ~10 tasks · hooks log every agent · board on disk, resumable
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

**C. Try it for one session without installing:**
```bash
claude --plugin-dir /path/to/bosun/plugins/bosun
```

Check it loaded: `claude plugin details bosun` should list Skills (11), Agents (10), Hooks (3).

## First run in a project

```text
/bosun:setup                      detect commands, write .bosun/config.json, keep .bosun/ out of git,
                                    and set worktree.baseRef = "head" (required for parallel builds; see below)
(start a new session if setup changed worktree.baseRef)
/bosun:plan a team task tracker with workspaces, kanban board and email notifications
/bosun:build                      runs the approved plan with parallel agents
/bosun:status --audit             any time, from the same session
/bosun:review                     final multi-lens review
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
| `/bosun:plan <idea>` | Clarifying questions, parallel scouts, architect writes `PLAN.md` + `tasks.json`, architecture and security critique, your approval. |
| `/bosun:build [plan]` | Executes a board: rolling pool of N agents in worktrees, review and security gates, merge, checks, monitor, resume (`--resume`), `--parallel`, `--review task\|batch\|final`, `--dry-run`. |
| `/bosun:status [--audit]` | Dashboard: progress, in flight, blocked, next, recent agent activity; `--audit` adds the monitor agent's health check. |
| `/bosun:investigate <symptom>` | Frame, reproduce, 2-5 hypotheses, one investigator per hypothesis in parallel, verifier, written report; `--fix` fixes test-first. |
| `/bosun:review [target]` | Lens reviewers in parallel (correctness, tests, security, design, performance, accessibility, api-compat), verified, de-duplicated report; `--fix`. |
| `/bosun:review-pr <n\|url>` | Same panel on a GitHub PR, checked out in a separate worktree; posts only after you approve the text. |
| `/bosun:security-audit [--full]` | Attack-surface map, installed scanners, security reviewers per area, verified findings, report; `--fix`. |
| `/bosun:commit` | Splits changes into logical commits, follows your convention, checks for secrets and leftovers, runs hooks, commits after you confirm. |
| `/bosun:ship` | Gate (lint, types, tests, build, quick review), push, PR from your template. Only runs when you type it. |
| `/bosun:setup` | One-time project setup (only runs when you type it). |

The agents can also be used directly, for example "use the bosun:security-reviewer agent on src/auth".

## Agents

| Agent | Role | Writes | Model / effort |
|---|---|---|---|
| `architect` | PLAN.md + task board; plan critique and revision | plan files | inherit / high |
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
3. **Gate per task.** A code-reviewer (correctness, plus tests for high-risk tasks) and a security-reviewer for sensitive tasks run in parallel. Doubtful blocking findings go to the verifier. Fix rounds go back to the same implementer. Then merge with `--no-ff`, fast checks, and the full suite every ~5 merges. A red merge is undone with `git revert`, never a reset.
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

Switches: `BOSUN_GUARD=0` turns the guard off. `BOSUN_ENFORCE_RESULT=1` makes a bosun agent continue once if it stops without a result block (off by default, because it could also fire when you stop an agent yourself).

The guard is a safety net against accidents, **not a security boundary**. It parses command text, so it can't see what a script does internally, and a determined agent could get around it. Keep your normal Claude Code permission settings.

Other built-in brakes: `ship` and `setup` only run when you type them; `review-pr` posts only text you approved; commit never pushes; no agent installs tools or touches remote services on its own.

## Configuration

`.bosun/config.json` (written by `/bosun:setup`; template in `plugins/bosun/templates/config.json`):

| Key | Meaning | Default |
|---|---|---|
| `commands.install/test/test_one/lint/typecheck/build/format/e2e` | exact commands; injected into every bosun agent at start | detected |
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

Levers: lower `max_parallel`; `review: batch`; implementers on `sonnet`; `--no-critique` for small plans; `/bosun:manager` already skips the crew for small changes.

The plugin also adds about **2.4k tokens to every session** for the skill and agent listings (`claude plugin details bosun` shows this). Disable it in projects where you don't use it (`/plugin`).

## What has been verified, and what hasn't

Verified while building this:
- the unit tests in `tests/` pass (task board scheduling, validation, locking under concurrent writes; guard rules including false-positive cases; hook events);
- `claude plugin validate --strict` passes for the plugin and the marketplace;
- installing from the local marketplace loads 11 skills, 10 agents and 3 hooks on Claude Code 2.1.301;
- the git commands the build skill prescribes were run in a scratch repository (worktrees, `--no-ff` merges, merge revert, path-limited commits for shared mode, cleanup after squash).

**Not verified: a full live multi-agent build.** That runs real Claude sessions on your account, so I didn't start one. Try it first on a small throwaway repository. LLM agents follow instructions imperfectly; the gates and the verifier reduce mistakes but don't remove them. Review the merged result before you ship.

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
  skills/<name>/SKILL.md               11 workflows (build/reference/execution.md holds edge cases)
  agents/<name>.md                     10 agents
  hooks/hooks.json + bosun_hooks.py    guard, activity log, context injection
  scripts/taskboard.py                 task board CLI (stdlib only)
  templates/config.json                project config template
examples/taskflow-40/                  40-task example plan (PLAN.md + tasks.json)
tests/                                 unit tests
LICENSE                                MIT
```

## Development

```bash
python3 -m unittest discover -s tests -v
claude plugin validate --strict ./plugins/bosun && claude plugin validate --strict .
claude plugin details bosun      # after installing from the local marketplace
```

## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md) for reporting vulnerabilities privately.

## License

[MIT](LICENSE)
