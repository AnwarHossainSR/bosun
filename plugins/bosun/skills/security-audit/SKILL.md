---
name: security-audit
description: Security review with parallel security agents - of the current branch's changes (default) or the whole codebase (--full). Maps the attack surface, runs scanners that are already installed, splits the review by area (auth, input handling, data and secrets, dependencies and infrastructure), verifies every serious finding, and writes a report with fixes. Use before shipping security-sensitive changes or for periodic audits.
argument-hint: "[--full | <base>...<head>] [--areas auth,input,data,deps-infra] [--fix]"
---

# bosun security-audit

Scope: $ARGUMENTS

## 1. Scope

- **Default (diff)**: the same target as the `bosun:review` skill (this branch against its base, plus uncommitted work).
- **`--full`**: the whole codebase. First build an attack-surface map, yourself for a small repository or with a `bosun:scout` for a large one: entry points (HTTP routes, RPC, CLI, queues, webhooks, uploads), authentication and authorization layers, data stores, outbound calls, secrets and config handling, dependency manifests, CI and infrastructure files.

## 2. Scanners (optional)

Check which tools are installed (`command -v gitleaks trufflehog semgrep osv-scanner pip-audit govulncheck cargo-audit trivy`, plus the package manager's audit command). Run the relevant ones and keep their output as leads for the reviewers. Don't install anything without asking. Note which tools weren't available.

## 3. Review in parallel

Split into areas, adjusted to the codebase (skip empty ones):
- **auth**: authentication, sessions, tokens, password and reset flows, authorization checks, tenant isolation;
- **input**: validation, injection (SQL, command, template), XSS and output encoding, SSRF, path traversal, uploads, deserialization;
- **data**: secrets and config, cryptography, PII and logging, error messages, security headers, CORS and CSRF;
- **deps-infra**: dependencies and supply chain, CI workflows, containers and infrastructure as code.

With `--areas`, review only the areas listed (comma-separated names from the list above, such as `--areas auth,input`); tell the user if a listed name doesn't match one of them. Without it, review every area that applies.

In one message, spawn one `bosun:security-reviewer` per selected area: mode `audit` with `--full`, mode `diff` otherwise (a small diff needs only one or two reviewers in total). Give each the scope (diff command or paths), its area, the attack-surface map, and the scanner leads for its area.

## 4. Verify

Send every critical and high finding, and any medium finding with low confidence, to `bosun:verifier`. Reproduction happens only locally (unit level, or against a server started on localhost), never against shared or production systems.

## 5. Report

Write `.bosun/reviews/<YYYY-MM-DD>-security.md`: overall risk; findings by severity (location, attacker, scenario, impact, fix, CWE when certain, verification status); controls that work; a hardening backlog; tools that ran and tools that weren't available. Never include secret values: give location and type only, and tell the user to rotate anything that looks real.

## 6. --fix

Fix confirmed findings through `bosun:implementer` (worktree), with a test that proves the fix where feasible. Gate each fix with `bosun:security-reviewer` in `diff` mode, then merge it into the current branch. Never commit directly to the default branch.
