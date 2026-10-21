# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - 2026-10-21

### Added
- The hooks save each bosun agent's report to disk: next to its plan (`.bosun/plans/<name>/results/`) when its result block names the board, else in `.bosun/results/`, as `<time>-<agent>-<task>-<id>.md`. The absolute path is logged as `saved` in `.bosun/activity.jsonl`. The manager no longer copies result blocks into report files, and points later agents to the saved file instead of pasting reports. A build checks after its first agent that the hooks ran, and falls back to saving reports itself.
- Newer Claude Code hands a subagent's report back through the `SubagentHandback` tool, so the agent's last message holds only closing text. A `PostToolUse` hook now saves and logs that report, and the stop that follows isn't flagged as missing a result block.
- The context injected into bosun agents tells them to run long commands (tests, builds, scanners) into a log and read its tail, and to keep prose before the BOSUN-RESULT block to three lines unless they were asked for a map or a threat model.
- The guard stops bosun agents other than the architect from running the task board's write commands (`init`, `set`, `add`, `sync`, `meta --set`); the manager is the board's only writer.
- `TB next --json` includes each task's `risk` and `spec_refs`, so the build's gate can pick its lenses without reading every brief.

### Changed
- About half the always-on cost: the skill and agent listings that load into every session dropped from about 2,560 to about 1,350 tokens (`claude plugin details bosun` estimates), with shorter descriptions and a shorter style rule in every skill and in the hook.
- Task agents read their own brief with `taskboard.py brief`, so the manager no longer retypes briefs and project commands into every prompt (agents from outside bosun still get them pasted). Reviewers get the brief command with the board's absolute path, and every agent's result block names its board.
- Smaller review panels for small diffs: a build task under about 200 changed lines gets one code-reviewer for all its lenses, and `/bosun:review` uses one code-reviewer for every lens but security under about 300 lines and 25 files. The code-reviewer accepts several lenses and tags each finding with its lens.
- `/bosun:review` and `/bosun:review-pr` read small diffs themselves but only the stat of large ones, and find content-based lens triggers (security above all) with `git diff --name-only -G`, so large PRs reach the reviewers sooner without skipping a security review; when unsure, the security lens runs.
- The build's resume procedure moved to `reference/execution.md`, read only when a build resumes, and an unfinished merge is now settled before any other resume action.
- Task board `--json` output is one compact line instead of indented JSON.
- Secret scanners in `/bosun:security-audit` run with redaction where supported, show only counts, and their logs are deleted after the report.
- README rewritten around a diagram of the workflow; developer details moved to CONTRIBUTING.md, and the code of conduct now adopts the Contributor Covenant by reference.

### Fixed
- The build's spot-check commits a task's leftover changes with path-limited commands and re-checks the diff, instead of `git add -A`.
- Resume marks a task done when its merge landed but the board has no commit for it, and never overwrites `base_commit`, which bounds the final review.
- The hooks never write through a symbolic link out of the project, never overwrite another agent's saved report, and still log a stop when an agent's message contains malformed Unicode.
- Every skill and agent description is plain YAML, so strict YAML parsers read the frontmatter too.

## [0.3.0] - 2026-10-19

### Added
- A local OpenSpec directory for projects that use OpenSpec themselves: set `planning.openspec_dir` to `.bosun/openspec`, with `openspec/**` in `protected_paths`. bosun's changes, tasks.md ticks and archived specs then stay in that git-ignored folder: the build never stages or commits them, agents in worktrees read the change from the main checkout, and `/bosun:archive` backs the folder up instead of committing. `/bosun:setup` offers it when the project already has its own `openspec/`, only together with an ignore rule for `.bosun/`, and `/bosun:build` stops and asks rather than commit a `.bosun/` OpenSpec directory that git doesn't ignore.
- `TB status --json` reports the resolved OpenSpec directory as `openspec.base`.

### Changed
- The task board reads the OpenSpec directory only from `planning.openspec_dir`. It no longer honours an undocumented `meta.openspec_dir` on a board, which the guard and the OpenSpec CLI calls never saw, so they could end up on different folders.

### Fixed
- OpenSpec CLI commands run from the OpenSpec directory's parent instead of the repository root. The CLI uses the nearest `openspec/` folder, so with a custom `planning.openspec_dir` it used to read the project's own specs, and validation and archiving could miss bosun's change or act on the wrong one.
- Skills and agents that named `openspec/` literally now follow `planning.openspec_dir`.

## [0.2.0] - 2026-10-19

### Added
- `/bosun:plan #123` (or an issue URL) plans from a GitHub issue: the issue is the brief, the proposal (PLAN.md for `--classic`) cites it, the board records it as `meta.issue`, and `/bosun:ship` links the PR with `Closes` or `Refs`. The manager routes an issue like any other goal: plan, investigate, or a single implementer for a small change.
- README: project-scope install (`--scope project`), following a branch with `owner/repo#ref`, how teammates get the plugin, installing in Claude Code on the web through the environment's setup script, and updating to a new version.
- `plugins/bosun/README.md`, a README inside the plugin folder for listings that show the plugin on its own, saying what bosun runs, writes and connects to; `homepage` in `plugin.json`.

### Changed
- The terse output style keeps logic words (because, so, but, not, only, can, may, must), text quoted from specs, tests and hypotheses, and full sentences for warnings, questions, statements of uncertainty and requests to confirm.

### Fixed
- `/bosun:build --resume`: an unfinished merge is no longer reported as a dirty tree to commit or stash (other changes still are); resume proposes what to do with it and settles it only after your go-ahead, and no task is merged while one is still open. Preflight no longer switches branches during a merge (`git checkout` of the current branch silently drops the merge state). An `in_progress` task is matched to its worktree by commit subject or files, not by board fields left over from an earlier attempt, and its uncommitted work in the task's files is committed with path-limited commands and continued instead of being reset; other paths are left for you to decide.
- `/bosun:ship` and `/bosun:commit` take `meta.issue` only from the board whose `meta.work_branch` is the current branch, and write an issue in another repository as `owner/repo#n`. Without a plan, ship links an issue the commits reference. Ship writes `Closes` only for PRs to the default branch, where GitHub acts on it, takes an existing PR's base as the base, and warns when a commit message would close the issue anyway; commit footers use `Refs` unless you ask for a closing keyword.
- The manager and `/bosun:investigate` treat issue text as a request from people, never as instructions, as `/bosun:plan` already did. The manager keeps the issue with the work on every route, so the PR can link it.
- `/bosun:review --fix` changes nothing unless every file it would touch holds exactly the reviewed code (right head checked out, no unstaged or uncommitted edits there).
- The SubagentStart hook no longer cuts the end of a long project profile (protected paths, main checkout, result reminder); it drops the last convention notes, then lists only as many protected paths as fit and counts the rest. The style rules keep `can`, `may` and `must` even when dropping hedges, and a test keeps every skill's style line in step with the hook.

## [0.1.0] - 2026-10-16

### Added
- Manager skill that routes any goal to the right workflow, and skills for plan, build, status, archive, investigate, review, review-pr, security-audit, commit, ship and setup.
- Spec-driven planning: `/bosun:plan` writes an OpenSpec-format change (proposal, delta specs with scenarios, design, tasks.md) plus a task board whose tasks reference the requirements they implement (`spec_refs`). `--classic` keeps the PLAN.md format.
- Task board commands for OpenSpec plans: `spec-check` (requirement coverage, tasks.md and board consistency, common format mistakes and deltas that archiving would refuse), `sync`, `add --spec-ref`, `init --openspec-change`; `set` ticks tasks.md, `brief` quotes the task's requirement blocks, `status` shows tasks.md progress.
- `/bosun:archive`: checks that every task is done and the change validates, then runs `openspec archive` and re-validates the main specs.
- `spec` review lens; implementers and test engineers write one test per scenario and report `spec_gaps`.
- Terse output style (`output_style`: caveman, caveman-lite, caveman-ultra or normal; default caveman), injected into bosun agents by the SubagentStart hook and applied by every skill.
- The guard keeps bosun agents other than the architect from editing OpenSpec files.
- Ten agents: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- Task board CLI (`taskboard.py`) with dependency- and file-ownership-aware scheduling, critical-path priority and locked atomic writes.
- Hooks: guard for bosun agents, activity log, project profile injection.
- 40-task example plan, and an OpenSpec example change validated in CI with the OpenSpec CLI.
- Open-source project files: CI, contributing guide, security policy, code of conduct, issue and pull request templates, CODEOWNERS, Dependabot for GitHub Actions.
