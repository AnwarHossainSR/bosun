---
name: security-audit
description: Security review of this branch's changes, or the whole codebase with --full, by parallel security agents, with verified findings and fixes. Use before shipping sensitive changes.
argument-hint: "[--full | <base>...<head>] [--areas auth,input,data,deps-infra] [--fix]"
---

# bosun security-audit

Scope: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Tokens:** before anything else, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py" start` and note the `mark:` it prints. At the end, run it with `report --since <mark>` and end your last message to the user (with `--fix`: after step 6) with its lines as printed, never in a file you write or text you post. Run by another skill (build, ship): skip both, the outer one reports. If the script fails, say so in one line.

## 1. Scope

- **Default (diff)**: the `bosun:review` skill's default target (this branch against its base, plus uncommitted work).
- **`--full`**: the whole codebase. First an attack-surface map, yourself for a small repository or with a `bosun:scout` for a large one: entry points (HTTP routes, RPC, CLI, queues, webhooks, uploads), authentication and authorization layers, data stores, outbound calls, secrets and config handling, dependency manifests, CI and infrastructure files.

## 2. Scanners (optional)

Check what's installed (`command -v gitleaks trufflehog semgrep osv-scanner pip-audit govulncheck cargo-audit trivy`, plus the package manager's audit command). Run the relevant ones, each into its own log (`set -o pipefail; log=$(mktemp); echo "log: $log"; <cmd> >"$log" 2>&1; code=$?; tail -n 40 "$log"; echo "exit $code"; (exit $code)`); when the tail doesn't show the findings, grep or read more of that log. Secret scanners print the secrets they find: run one only in a mode that redacts them (gitleaks: `--redact`), and skip one that can't, noting it as unsafe to run here; for those, show only the exit status and finding count instead of the tail. Delete every scanner log once the report is written. Keep the output as leads for the reviewers. Install nothing without asking. Note which tools weren't available.

## 3. Review in parallel

Areas, adjusted to the codebase (skip empty ones):
- **auth**: authentication, sessions, tokens, password and reset flows, authorization checks, tenant isolation;
- **input**: validation, injection (SQL, command, template), XSS and output encoding, SSRF, path traversal, uploads, deserialization;
- **data**: secrets and config, cryptography, PII and logging, error messages, security headers, CORS and CSRF;
- **deps-infra**: dependencies and supply chain, CI workflows, containers and infrastructure as code.

`--areas` reviews only the listed areas (comma-separated names from the list, such as `--areas auth,input`); tell the user if a name doesn't match one. Without it, every area that applies.

In one message, spawn the `bosun:security-reviewer` agents, mode `audit` with `--full`, mode `diff` otherwise: one per selected area, or for a small diff one or two in total with every selected area assigned to one of them. Each gets the scope (diff command or paths), its areas, the attack-surface map, and the scanner leads (log paths) for those areas.

## 4. Verify

Every critical and high finding, and any medium one with low confidence, goes to `bosun:verifier`. Reproduction happens only locally (unit level, or against a server started on localhost), never against shared or production systems.

## 5. Report

Write `.bosun/reviews/<YYYY-MM-DD>-security.md`, and show the user, in the review skill's step 6 layout: overall risk as the heading (🔴, 🟠, 🟡 or 🔵 with the level; `## ✅ No findings` when there are none), the count table without nits, findings by severity (location, attacker, scenario, impact, fix, CWE when certain, and the verification: ✅ or ❔ from the verifier, else the reviewer's confidence); controls that work; a hardening backlog; tools that ran and tools that weren't available. Never include secret values: location and type only, and tell the user to rotate anything that looks real.

## 6. --fix

Fix confirmed findings through `bosun:implementer` (worktree), with a test that proves the fix where feasible. Gate each fix with `bosun:security-reviewer` in `diff` mode, show the gated fixes, and merge them into the current branch only after the user's go-ahead. On the default branch, create or ask for a work branch first: never commit directly to the default branch.
