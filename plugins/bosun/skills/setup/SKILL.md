---
name: setup
description: One-time bosun setup - detect commands, OpenSpec and conventions, write .bosun/config.json, keep .bosun/ out of git, check the worktree setting.
argument-hint: "[--force]"
disable-model-invocation: true
---

# bosun setup

Arguments: $ARGUMENTS

Configure this repository for bosun. Change nothing before showing the user what you'll change; ask once for the whole batch.

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

## 1. Inspect (read-only)

- **Repository:** `git rev-parse --show-toplevel`, current branch, default branch (`git symbolic-ref --short refs/remotes/origin/HEAD`, falling back to `main` or `master`), `git remote -v`, `gh auth status` (needed only for PR features). Not a git repo: say worktree isolation is unavailable, use shared mode, continue.
- **Existing setup:** `.bosun/config.json` (keep it unless `--force`; offer to update individual fields), CLAUDE.md, AGENTS.md.
- **Commands.** Trust, in order: CI workflows (`.github/workflows/*`, `.gitlab-ci.yml` and similar: what CI runs is the ground truth), task runners (`package.json` scripts, `Makefile`, `justfile`, `Taskfile.yml`), language defaults.
  - JS/TS: package manager from the lockfile (`pnpm-lock.yaml` → pnpm, `yarn.lock` → yarn, `bun.lock`/`bun.lockb` → bun, `package-lock.json` → npm); monorepo tooling (`pnpm-workspace.yaml`, `turbo.json`, `nx.json`).
  - Python: `pyproject.toml` (uv, poetry, hatch, pdm), `requirements*.txt`, pytest, ruff and mypy config.
  - Go `go.mod`, Rust `Cargo.toml`, JVM `pom.xml` or `build.gradle(.kts)` and wrappers, Ruby `Gemfile`, PHP `composer.json`, .NET `*.sln`/`*.csproj`. Anything else: say so and ask.
  Record a command only if it really exists (the script, target or tool is there).
- **Commit convention:** `git log --format=%s -30` plus any commitlint config: conventional, gitmoji, ticket-prefix, or freeform.
- **OpenSpec:** whether `openspec/` exists (config.yaml, specs/, changes/), whether git ignores it (`git check-ignore -q openspec/changes`), whether its changes belong to bosun (a `.bosun/plans/*/tasks.json` with that `meta.openspec_change`) or to the project, `command -v openspec` and `openspec --version`. The CLI is optional for planning and building and required for `/bosun:archive`. It sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0` (or `DO_NOT_TRACK=1`) is set; tell the user before they install it.
- **Protected paths to suggest:** CI workflows, applied migrations, generated or vendored code, secret files, release config.

## 2. Propose `.bosun/config.json`

Start from `${CLAUDE_PLUGIN_ROOT}/templates/config.json`. Fill in exact command strings; `test_one` uses `{path}` for a single test file (for example `pnpm vitest run {path}`). Unknown commands stay `""`. Defaults: `build.max_parallel` 4 (3 for heavy test suites or small machines), `isolation` `worktree` (`shared` outside git), `review` `task`, `security_review` `sensitive`, `max_attempts` 2, `merge` `merge`.

- `planning.format`: `openspec` (default; plans are OpenSpec changes with requirements and scenarios) or `plan` (classic PLAN.md). `planning.openspec_dir`: `openspec` unless the repository keeps OpenSpec elsewhere. The project already uses OpenSpec for its own work (an `openspec/` whose changes no bosun board links), or the user wants bosun's specs out of git: recommend `.bosun/openspec`. bosun's changes then live in its own local folder, apart from the project's specs, are never committed, and still work with the OpenSpec CLI (bosun runs it from `.bosun/`). With that choice, also propose `openspec/**` in `protected_paths`, so bosun agents never edit the project's own specs. `.bosun/openspec` is local only while git ignores it, so it depends on the git hygiene in section 3: if git doesn't ignore `.bosun/` yet and the user declines both ignore options, don't set `.bosun/openspec`; say why and ask what to do instead.
- `output_style`: `caveman` (default; terse agent reports and updates, so fewer output tokens), `caveman-lite`, `caveman-ultra`, or `normal`. It shortens prose only: code, commits, PR text, docs and specs are written normally. Savings depend on the work; don't promise a number.

## 3. Propose git hygiene

`.bosun/` holds plans, reports, agent results, logs and scratch files; `.claude/worktrees/` holds agent worktrees. Neither should show up as untracked files. Offer one of:
- (recommended) append both to `.git/info/exclude`: local only, nothing to commit;
- add both to `.gitignore`: shared with the team.

A team that wants plans in version control can ignore `.bosun/*` but keep `!.bosun/plans/`. Don't ignore a shared `planning.openspec_dir` such as `openspec/`: its specs and archived changes are meant to be committed. A local one under `.bosun/` is ignored on purpose, and a project that ignores its own `openspec/` should use `.bosun/openspec` for bosun.

## 4. Worktree base (important)

In worktree mode every implementer works in its own git worktree. By default Claude Code branches new worktrees from the repository's **default branch**, so a task wouldn't see work already merged into the build's integration branch. bosun needs worktrees branched from the current HEAD:

```json
{ "worktree": { "baseRef": "head" } }
```

Check `.claude/settings.local.json`, `.claude/settings.json` and `~/.claude/settings.json` for `worktree.baseRef`. None sets it to `"head"`: offer to merge it into `.claude/settings.local.json` (personal, not committed), preserving every existing key. Tell the user to start a new session afterwards to be safe; whether a running session picks the change up is not documented.

## 5. Worktree environment

Fresh worktrees contain only tracked files.
- Gitignored files such as `.env` or `.env.local` needed to run tests: offer a `.worktreeinclude` file (gitignore syntax) listing them; Claude Code copies matching gitignored files into each new worktree. Warn that this copies secrets into worktree folders inside the repo (they stay ignored).
- Dependencies aren't shared between worktrees: each implementer runs `commands.install` first, which costs time per task. Fast installers (pnpm, uv, bun) or a warm package cache help.

## 6. Fewer permission prompts (optional)

A build runs many git and task-board commands. Explain the options instead of changing permissions silently:
- choose "Yes, and don't ask again" the first time each command is requested (Claude Code saves a rule per command prefix and repository); or
- add allow rules to `.claude/settings.local.json` under `permissions.allow`, such as `"Bash(git worktree *)"`, `"Bash(git merge *)"`, `"Bash(git branch -d *)"` and the project's test and lint commands; or
- run long builds in auto mode.

Write permission rules only if the user asks.

## 7. Summary

List what was written or changed. With `planning.openspec_dir` set to `.bosun/openspec`, run `git check-ignore -v .bosun/openspec/changes` and show the rule it prints; nothing printed means the folder isn't local: fix the ignore rule before any planning. Next steps: `/bosun:plan <idea>` for a new product or feature, `/bosun:manager <goal>` for anything else.
