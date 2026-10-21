---
name: commit
description: Turn current changes into clean commits in the repository's convention, after checks for secrets and leftovers; commits after you confirm, never pushes. Use when asked to commit.
argument-hint: "[hint about the change] [--yes] [--amend]"
---

# bosun commit

Arguments: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

## 1. Inspect

`git status --porcelain=v1 -b`, `git diff --cached --stat`, `git diff --stat`, `git ls-files --others --exclude-standard`, `git log --format=%s -20`, `git log -3 --format=%B`, the branch name (it may hold a ticket id such as ABC-123), and any commit-message config (`commitlint.config.*`, `.commitlintrc*`, `.czrc`, a `commitlint` key in package.json). A merge, rebase or cherry-pick in progress: say so and stop.

## 2. Convention

Commitlint rules first; otherwise the dominant style in recent history (Conventional Commits `type(scope): subject`, gitmoji, ticket prefixes, plain sentences). No signal: Conventional Commits.

## 3. What goes into each commit

- Something staged: commit exactly that. Mention other changes, but don't add them without asking.
- Nothing staged: group the changes into logical commits, one concern each (feature, fix, refactor, formatting, dependencies, docs). Tests stay with the code they test; generated files and lockfiles go with the change that produced them.
- Stage whole files with `git add -- <paths>`. There's no interactive hunk staging, so a file mixing concerns stays in one commit; say so.

## 4. Check exactly what will be committed (`git diff --cached`, per commit)

- **Stop and tell the user** about secrets (private keys, tokens, passwords, `.env` files, cloud credentials, connection strings with passwords), merge conflict markers, and files over about 5 MB unless the repository already tracks files like them.
- **Warn** about debug output (`console.log`, `print(`, `dbg!`, `debugger`), focused or skipped tests (`.only`, `fdescribe`, `xit`, skip markers), new TODO or FIXME without context, blocks of commented-out code.

Never print a secret's value; give the file and line.

## 5. Write the message

- Subject: imperative mood, 72 characters at most (aim for 50), no trailing period, type and scope per the convention, the change from the reader's point of view.
- Body, unless trivial, wrapped at 72 columns: what changed and why (not how), notable trade-offs, migration notes.
- Footers: `BREAKING CHANGE: ...` when it applies. Issue references only when you actually know them (branch name, the user, or `meta.issue` of the bosun board whose `meta.work_branch` is the current branch): `#<n>`, or `<owner>/<repo>#<n>` for another repository, in a reference footer such as `Refs: #<n>`. A closing keyword (`Closes`, `Fixes`) only when the user asks: `/bosun:ship` decides whether the PR closes the issue. Never invent issue numbers. Add any trailers the project or the user requires.

## 6. Confirm and commit

Show the plan: each commit with its files and full message. Commit after the user approves, or at once with `--yes`. One commit at a time: stage its files, write the message to a temp file, `git commit -F <file>`.

A failing hook: read its output. Fix purely mechanical problems (formatter, lint autofix) and retry once; otherwise stop and report. Never `--no-verify` unless the user explicitly asks.

`--amend` only when the last commit provably hasn't been pushed. Remote-tracking refs can be stale, so refresh first: `git fetch --quiet <remote>` (the branch's upstream remote, usually `origin`). Fetch fails: refuse, because the remote state can't be established. After a successful fetch, refuse if `git branch -r --contains HEAD` prints anything. No remote configured: nothing can have been pushed, amending is fine. When you refuse, explain why.

## 7. Finish

Show `git log --oneline -n <number of new commits>` and `git status -sb`. Don't push. Branch ready: mention `/bosun:ship`.
