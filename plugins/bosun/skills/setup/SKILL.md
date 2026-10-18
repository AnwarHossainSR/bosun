---
name: setup
description: One-time bosun setup for the current repository. Detects the stack and its install, test, lint, typecheck and build commands, OpenSpec, and the planning format and output style to use, writes .bosun/config.json, keeps .bosun/ and agent worktrees out of git, and checks the worktree setting that parallel agents need. Run before the first /bosun:build in a repo, or when the commands change.
argument-hint: "[--force]"
disable-model-invocation: true
---

# bosun setup

Arguments: $ARGUMENTS

Configure this repository for bosun. Change nothing before showing the user what you'll change; ask once for the whole batch.

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, can, may, must); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

## 1. Inspect (read-only)

- **Repository.** `git rev-parse --show-toplevel`, current branch, default branch (`git symbolic-ref --short refs/remotes/origin/HEAD`, falling back to `main` or `master`), `git remote -v`, and `gh auth status` (needed only for PR features). Not a git repo: say worktree isolation is unavailable, use shared mode, and continue.
- **Existing setup.** `.bosun/config.json` (keep it unless `--force`; offer to update individual fields), CLAUDE.md, AGENTS.md.
- **Commands.** Trust sources in this order: CI workflows (`.github/workflows/*`, `.gitlab-ci.yml`, and similar: what CI runs is the ground truth), then task runners (`package.json` scripts, `Makefile`, `justfile`, `Taskfile.yml`), then language defaults.
  - JS/TS: package manager from the lockfile (`pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `bun.lock`/`bun.lockb` → bun, `package-lock.json` → npm); monorepo tooling (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`).
  - Python: `pyproject.toml` (uv, poetry, hatch, pdm), `requirements*.txt`, pytest, ruff and mypy config.
  - Go `go.mod`, Rust `Cargo.toml`, JVM `pom.xml` or `build.gradle(.kts)` and wrappers, Ruby `Gemfile`, PHP `composer.json`, .NET `*.sln`/`*.csproj`. Anything else: say so and ask.
  Record a command only if it really exists (the script, target or tool is there).
- **Commit convention.** `git log --format=%s -30` plus any commitlint config: conventional, gitmoji, ticket-prefix, or freeform.
- **OpenSpec.** Whether `openspec/` exists (config.yaml, specs/, changes/), `command -v openspec` and `openspec --version`. The CLI is optional for planning and building, and required for `/bosun:archive`. It sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0` (or `DO_NOT_TRACK=1`) is set; tell the user before they install it.
- **Protected paths to suggest.** CI workflows, applied migrations, generated or vendored code, secret files, release config.

## 2. Propose `.bosun/config.json`

Start from `${CLAUDE_PLUGIN_ROOT}/templates/config.json`. Fill in exact command strings; `test_one` uses `{path}` for a single test file (for example `pnpm vitest run {path}`). Leave unknown commands as `""`. Defaults: `build.max_parallel` 4 (3 for heavy test suites or small machines), `isolation` `worktree` (`shared` outside git), `review` `task`, `security_review` `sensitive`, `max_attempts` 2, `merge` `merge`.

- `planning.format`: `openspec` (default; plans are OpenSpec changes with requirements and scenarios) or `plan` (classic PLAN.md). `planning.openspec_dir`: `openspec` unless the repository keeps OpenSpec elsewhere.
- `output_style`: `caveman` (default; terse agent reports and updates, so fewer output tokens), `caveman-lite`, `caveman-ultra`, or `normal`. It shortens prose only: code, commits, PR text, docs and specs are written normally. Savings depend on the work; don't promise a number.

## 3. Propose git hygiene

`.bosun/` holds plans, reports, logs and scratch files; `.claude/worktrees/` holds agent worktrees. Neither should show up as untracked files. Offer one of:
- (recommended) append both to `.git/info/exclude`: local only, nothing to commit;
- add both to `.gitignore`: shared with the team.
If the team wants plans in version control, they can ignore `.bosun/*` but keep `!.bosun/plans/`. Never ignore `openspec/`: the specs and archived changes are meant to be committed.

## 4. Worktree base (important)

In worktree mode every implementer works in its own git worktree. By default Claude Code branches new worktrees from the repository's **default branch**, so a task would not see work already merged into the build's integration branch. bosun needs worktrees branched from the current HEAD:

```json
{ "worktree": { "baseRef": "head" } }
```

Check `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json` for `worktree.baseRef`. If none sets it to `"head"`, offer to merge it into `.claude/settings.local.json` (personal, not committed) while preserving every existing key. Tell the user to start a new session afterwards to be safe; whether a running session picks the change up is not documented.

## 5. Worktree environment

Fresh worktrees contain only tracked files.
- If gitignored files such as `.env` or `.env.local` are needed to run tests, offer a `.worktreeinclude` file (gitignore syntax) listing them; Claude Code copies matching gitignored files into each new worktree. Warn that this copies secrets into worktree folders inside the repo (they stay ignored).
- Dependencies are not shared between worktrees: each implementer runs `commands.install` first, which costs time per task. Fast installers (pnpm, uv, bun) or a warm package cache help.

## 6. Fewer permission prompts (optional)

A build runs many git and task-board commands. Explain the options instead of changing permissions silently:
- choose "Yes, and don't ask again" the first time each command is requested (Claude Code saves a rule per command prefix and repository); or
- add allow rules to `.claude/settings.local.json` under `permissions.allow`, such as `"Bash(git worktree *)"`, `"Bash(git merge *)"`, `"Bash(git branch -d *)"` and the project's test and lint commands; or
- run long builds in auto mode.
Only write permission rules if the user asks you to.

## 7. Summary

List what was written or changed. Next steps: `/bosun:plan <idea>` for a new product or feature, or `/bosun:manager <goal>` for anything else.
