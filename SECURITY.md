# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** (or go to <https://github.com/AnwarHossainSR/bosun/security/advisories/new>). Please don't open a public issue.

Include what you found, how to reproduce it, the impact you expect, and the bosun commit and Claude Code version you tested with.

bosun is maintained by volunteers, so there's no guaranteed response time. Reports are acknowledged and handled on a best-effort basis, and fixes are credited to reporters who want credit.

## Supported versions

Security fixes go to the latest release and the `main` branch.

## Scope

In scope:
- the task board script and the hooks (`plugins/bosun/scripts/`, `plugins/bosun/hooks/`), for example a crafted `tasks.json` or hook input that escapes the project directory;
- skill or agent instructions that would make Claude take a destructive or outward-facing action (push, publish, post) without the user asking.

Please keep in mind:
- The guard hook is a safety net against accidents by bosun's own agents, **not a security boundary**. It parses command text and can be bypassed by indirection; Claude Code's own permission settings remain the real control. Bypasses that an agent could plausibly hit by accident are still worth reporting.
- bosun runs inside Claude Code and inherits its permission model. Issues in Claude Code itself should go to Anthropic.
