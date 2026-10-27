<div align="center">

# bosun

**Your AI dev crew for Claude Code.**

Spec-driven plans, right-sized builds and verified reviews, from one command.

[![CI](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml/badge.svg)](https://github.com/AnwarHossainSR/bosun/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757.svg)](https://code.claude.com/docs/en/plugins)

</div>

On a ship, the bosun runs the deck crew. **bosun** runs a crew of Claude Code agents: give it a goal, and a manager picks the lightest workflow, then specialist agents plan, build, review and ship it, with review gates along the way.

<p align="center">
  <img src="docs/bosun-flow.svg" width="100%" alt="How bosun works: your goal goes to the manager, which runs plan, build, review and ship with specialist agents sized to the work">
</p>

## Highlights

- **Spec first.** Plans are [OpenSpec](https://github.com/Fission-AI/OpenSpec) changes with testable scenarios, and nothing is built until you approve.
- **Right-sized.** Small work gets one implementer and one review; big plans get a parallel crew in git worktrees.
- **Reviews you can act on.** Findings are ranked 🔴 🟠 🟡 🔵 ⚪, verified, and each comes with its file, line and a fix.
- **Lean.** About 1k tokens of always-on context, and reports end with what the run cost.
- **Safe by default.** A guard stops bosun's agents from pushing, rewriting history or editing protected paths.

## Quick start

```bash
claude plugin marketplace add AnwarHossainSR/bosun
claude plugin install bosun@bosun-marketplace
```

Then, in Claude Code inside your project:

```text
/bosun:setup                          one-time: detects your commands, writes .bosun/config.json
/bosun:propose add CSV export         an OpenSpec change and task board, for your approval
/bosun:apply                          builds it task by task, with review gates
/bosun:review                         verified multi-lens review of your branch
/bosun:ship                           final checks, push and pull request (asks first)
```

Not sure which command fits? `/bosun:manager <goal in plain words>` picks one for you.

## Commands

| Command | What it does |
|---|---|
| `/bosun:manager <goal>` | Routes any goal to the lightest workflow |
| `/bosun:propose <idea \| #issue>` | Plans a change: OpenSpec spec, design and task board (also `/bosun:plan`) |
| `/bosun:apply [plan]` | Builds an approved plan, solo or with a parallel crew (also `/bosun:build`) |
| `/bosun:status` | Progress, blocked tasks and what's next |
| `/bosun:review [target]` | Reviews local changes; `--fix` applies confirmed fixes |
| `/bosun:review-pr <n \| url>` | Reviews a GitHub pull request; posts only what you approve |
| `/bosun:investigate <symptom>` | Finds a bug's root cause with parallel hypotheses |
| `/bosun:security-audit` | Security review of the branch, or the codebase with `--full` |
| `/bosun:commit` | Clean commits in your convention; never pushes |
| `/bosun:ship` | Final checks, push and pull request |
| `/bosun:archive [id]` | Merges a finished change into the main specs |
| `/bosun:setup` | One-time project setup |

Flags and details for every command are in the [guide](docs/guide.md#commands).

## Install in a new repository

1. **Prerequisites:** Claude Code 2.1.240 or later, git and Python 3.10+ as `python3`. PR features need the GitHub CLI (`gh auth login`); the [OpenSpec CLI](https://github.com/Fission-AI/OpenSpec) is optional and only `/bosun:archive` needs it.
2. **Add the marketplace** (once per machine): `claude plugin marketplace add AnwarHossainSR/bosun`
3. **Install from inside the repository,** choosing who gets it:

   | Scope | Command |
   |---|---|
   | Just you, this repository | `claude plugin install bosun@bosun-marketplace --scope local` |
   | Everyone on the repository | `claude plugin install bosun@bosun-marketplace --scope project`, then commit `.claude/settings.json` |
   | Just you, every repository | `claude plugin install bosun@bosun-marketplace` |

4. **Open a new Claude Code session** there and run `/bosun:setup`. It shows what it will write and asks once: `.bosun/config.json`, ignore rules for `.bosun/` and `.claude/worktrees/`, and the `worktree.baseRef` setting builds need. Already using OpenSpec for your own specs? Choose `.bosun/openspec` when it asks.
5. **Check it:** `claude plugin details bosun` lists 14 skills, 10 agents and 4 hooks.

**Update:** `claude plugin marketplace update bosun-marketplace`, then `claude plugin update bosun@bosun-marketplace --scope <scope>`, and start a new session. **Remove:** `claude plugin uninstall bosun@bosun-marketplace --scope <scope>`; your `.bosun/` folder stays until you delete it. Cloud sessions and trying it without installing: see the [guide](docs/guide.md#more-install-options).

## Learn more

- **[Guide](docs/guide.md):** how plans and builds run, reviews, the agents, token use, configuration and safety
- **[Changelog](CHANGELOG.md)** · **[Contributing](CONTRIBUTING.md)** · **[Security](SECURITY.md)**

bosun is young: start with a small plan, and review merged work before you ship it. The guard is a safety net against accidents, not a security boundary, so keep your usual Claude Code permission settings.

## License

[MIT](LICENSE)
