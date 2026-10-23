# bosun

Your AI dev crew for Claude Code. A manager skill takes a goal and picks the lightest workflow: a spec-first plan (an OpenSpec-format change with testable scenarios) built by one implementer task by task or, for a big plan, by parallel agents in git worktrees; an investigation, a multi-lens review, a security audit, or a single agent for a small change. Ten specialist agents do the work, a task board schedules them by dependencies and file ownership, and, with the default review policy, all work is reviewed before it's merged.

Full documentation: <https://github.com/AnwarHossainSR/bosun#readme>

## What it adds

- **14 skills**: `manager`, `plan`, `build`, `status`, `archive`, `investigate`, `review`, `review-pr`, `security-audit`, `commit`, `ship`, `setup`, and `propose` and `apply`, OpenSpec's names for `plan` and `build`. `ship`, `setup`, `archive`, `propose` and `apply` run only when you type them.
- **10 agents**: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- **4 hooks**, which act only on bosun's own agents (`agent_type` starting with `bosun:`): a guard before Bash and file edits; the project profile and output style when an agent starts; and, when it stops or hands back its report, an activity log entry plus a copy of the report next to its plan (`.bosun/plans/<name>/results/`, or `.bosun/results/`).

## What it runs, writes and connects to

- **Runs on your machine:** `git` (worktrees, branches, merges and commits on a work branch), `python3` for the task board (`scripts/taskboard.py`), the token report (`scripts/usage.py`) and the hooks (`hooks/bosun_hooks.py`), all standard library only, and your project's own install, test, lint, typecheck and build commands.
- **Reads:** for its token report, Claude Code's transcript files under `~/.claude/projects/` (or `$CLAUDE_CONFIG_DIR/projects/`): this session's, plus the first lines of recent ones when it must work out which file is this session's. `usage.py` makes no network calls; only the token lines it prints go into the conversation.
- **Writes:** `.bosun/` in your project (config, task boards, agent results, reports, reviews, investigations, scratch files, `activity.jsonl`), plan files under `openspec/`, `.bosun/openspec/` (a local, git-ignored choice for projects with their own OpenSpec) or `.bosun/plans/`, and the code changes its agents make. `/bosun:setup` shows its changes and asks once before writing them: `.bosun/config.json`, ignore entries for `.bosun/` and agent worktrees, `worktree.baseRef` in `.claude/settings.local.json`, and only if you want them, a `.worktreeinclude` file or permission rules.
- **Network:** the hooks and the task board make no network calls and send no telemetry. Skills use the GitHub CLI (`gh`) to read issues and pull requests; `/bosun:review-pr` posts only text you approved, and `/bosun:ship` pushes and opens a pull request only after you confirm. Some agents (architect, implementer, investigator, scout, security-reviewer, test-engineer) can use Claude Code's web search and fetch tools for research. The OpenSpec CLI is optional and never installed without asking; it sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0` is set, which bosun sets on the commands it runs.

The guard is a safety net against accidents, not a security boundary. Keep your normal Claude Code permission settings.

## Where it works

Claude Code with git and Python 3.10+ (validated and installed on Claude Code 2.1.240, 2.1.303 and 2.1.306). On claude.ai chat, plugin agents and hooks don't load, so bosun isn't useful there; Cowork hasn't been tested.

## Install

```bash
claude plugin marketplace add AnwarHossainSR/bosun
claude plugin install bosun@bosun-marketplace
```

Then run `/bosun:setup` in your project. Update later with `claude plugin update bosun@bosun-marketplace` (add the `--scope` you installed with).

## License

MIT
