# bosun

A multi-agent software delivery crew for Claude Code. A manager skill takes a goal and picks the lightest workflow: a spec-first plan (OpenSpec-format change with testable scenarios) built by parallel agents in git worktrees, an investigation, a multi-lens review, a security audit, or a single agent for a small change. Ten specialist agents do the work; a task board schedules them by dependencies and file ownership; by default every task is reviewed before it is merged.

Full documentation, including what has and hasn't been verified: <https://github.com/AnwarHossainSR/bosun#readme>

## What it adds

- **12 skills**: `manager`, `plan`, `build`, `status`, `archive`, `investigate`, `review`, `review-pr`, `security-audit`, `commit`, `ship`, `setup`. `ship`, `setup` and `archive` run only when you type them.
- **10 agents**: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- **3 hooks**, which act only on bosun's own agents (`agent_type` starting with `bosun:`): a guard before Bash and file edits, project-profile and output-style injection when an agent starts, and an activity log entry when an agent starts and stops.

## What it runs, writes and connects to

- **Runs on your machine:** `git` (worktrees, branches, merges and commits on a work branch), `python3` for the task board (`scripts/taskboard.py`) and the hooks (`hooks/bosun_hooks.py`), both standard library only, and your project's own install, test, lint, typecheck and build commands.
- **Writes:** `.bosun/` in your project (config, task boards, reports, reviews, investigations, scratch files, `activity.jsonl`), plan files under `openspec/`, `.bosun/openspec/` (a local, git-ignored choice for projects with their own OpenSpec) or `.bosun/plans/`, and the code changes its agents make. `/bosun:setup` shows its changes and asks once before writing them: `.bosun/config.json`, `.gitignore` entries for `.bosun/` and agent worktrees, `worktree.baseRef` in `.claude/settings.local.json`, and only if you want them, a `.worktreeinclude` file or permission rules.
- **Network:** the hooks and the task board make no network calls and send no telemetry. Skills use the GitHub CLI (`gh`) to read issues and pull requests; `/bosun:review-pr` posts only text you approved, and `/bosun:ship` pushes and opens a pull request only after you confirm. Some agents (architect, implementer, investigator, scout, security-reviewer, test-engineer) can use Claude Code's web search and fetch tools for research. The OpenSpec CLI is optional and never installed without asking; it sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0` is set, which bosun sets on the commands it runs.

The guard is a safety net against accidents, not a security boundary. Keep your normal Claude Code permission settings.

## Where it works

Built and tested for Claude Code (2.1.301) with git and Python 3.10+. On claude.ai chat, plugin agents and hooks don't load, so bosun is not useful there; Cowork hasn't been tested.

## Install

```bash
claude plugin marketplace add AnwarHossainSR/bosun
claude plugin install bosun@bosun-marketplace
```

Then run `/bosun:setup` in your project. Update later with `claude plugin update bosun@bosun-marketplace`.

## License

MIT
