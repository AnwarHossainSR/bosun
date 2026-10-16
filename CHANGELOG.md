# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `/bosun:plan #123` (or an issue URL) plans from a GitHub issue: the issue is the brief, the proposal cites it, the board records it as `meta.issue`, and `/bosun:ship` links the PR with `Closes` or `Refs`. The manager routes issues to plan or investigate.
- README: project-scope install (`--scope project`), following a branch with `owner/repo#ref`, how teammates get the plugin, and installing in Claude Code on the web through the environment's setup script.
- Manager skill that routes any goal to the right workflow, and skills for plan, build, status, archive, investigate, review, review-pr, security-audit, commit, ship and setup.
- Spec-driven planning: `/bosun:plan` writes an OpenSpec-format change (proposal, delta specs with scenarios, design, tasks.md) plus a task board whose tasks reference the requirements they implement (`spec_refs`). `--classic` keeps the PLAN.md format.
- Task board commands for OpenSpec plans: `spec-check` (requirement coverage, tasks.md and board consistency, common format mistakes and deltas that archiving would refuse), `sync`, `add --spec-ref`, `init --openspec-change`; `set` ticks tasks.md, `brief` quotes the task's requirement blocks, `status` shows tasks.md progress.
- `/bosun:archive`: checks that every task is done and the change validates, then runs `openspec archive` and re-validates the main specs.
- `spec` review lens; implementers and test engineers write one test per scenario and report `spec_gaps`.
- Terse output style (`output_style`: caveman, caveman-lite, caveman-ultra or normal; default caveman), injected into bosun agents by the SubagentStart hook and applied by every skill. It keeps logic words, quoted spec and test text, and full sentences for warnings, questions, uncertainty and requests to confirm.
- The guard keeps bosun agents other than the architect from editing OpenSpec files.
- Ten agents: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- Task board CLI (`taskboard.py`) with dependency- and file-ownership-aware scheduling, critical-path priority and locked atomic writes.
- Hooks: guard for bosun agents, activity log, project profile injection.
- 40-task example plan, and an OpenSpec example change validated in CI with the OpenSpec CLI.
- Open-source project files: CI, contributing guide, security policy, code of conduct, issue and pull request templates, CODEOWNERS, Dependabot for GitHub Actions.
