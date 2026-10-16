# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Manager skill that routes any goal to the right workflow, and skills for plan, build, status, investigate, review, review-pr, security-audit, commit, ship and setup.
- Ten agents: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- Task board CLI (`taskboard.py`) with dependency- and file-ownership-aware scheduling, critical-path priority and locked atomic writes.
- Hooks: guard for bosun agents, activity log, project profile injection.
- 40-task example plan.
- Open-source project files: CI, contributing guide, security policy, code of conduct, issue and pull request templates, CODEOWNERS, Dependabot for GitHub Actions.
