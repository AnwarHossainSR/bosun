---
name: commit
description: Turn the current changes into clean commits. Reads staged and unstaged changes, follows the repository's commit convention, splits unrelated changes into logical commits, checks for secrets, conflict markers and debug leftovers, runs the hooks, and commits after you confirm. Never pushes. Use when the user asks to commit or to write a commit message.
argument-hint: "[hint about the change] [--yes] [--amend]"
---

# bosun commit

Arguments: $ARGUMENTS

## 1. Inspect

`git status --porcelain=v1 -b`, `git diff --cached --stat`, `git diff --stat`, `git ls-files --others --exclude-standard`, `git log --format=%s -20`, `git log -3 --format=%B`, the branch name (it may contain a ticket id such as ABC-123), and any commit-message config (`commitlint.config.*`, `.commitlintrc*`, `.czrc`, a `commitlint` key in package.json). If a merge, rebase or cherry-pick is in progress, say so and stop.

## 2. Convention

Follow the repository: commitlint rules first; otherwise the dominant style in recent history (Conventional Commits `type(scope): subject`, gitmoji, ticket prefixes, plain sentences). Use Conventional Commits when history gives no signal.

## 3. Decide what goes into each commit

- Something is staged: commit exactly that. Mention other changes, but don't add them without asking.
- Nothing staged: group the changes into logical commits, one concern each (feature, fix, refactor, formatting, dependencies, docs). Tests stay with the code they test. Generated files and lockfiles go with the change that produced them.
- Stage whole files with `git add -- <paths>`. There's no interactive hunk staging here, so if one file mixes concerns, keep it in one commit and say so.

## 4. Check exactly what will be committed (`git diff --cached`, per commit)

- **Stop and tell the user** about: secrets (private keys, tokens, passwords, `.env` files, cloud credentials, connection strings with passwords), merge conflict markers, and files over about 5 MB unless the repository already tracks files like them.
- **Warn** about: debug output (`console.log`, `print(`, `dbg!`, `debugger`), focused or skipped tests (`.only`, `fdescribe`, `xit`, skip markers), new TODO or FIXME without context, blocks of commented-out code.

Never print a secret's value; give the file and line.

## 5. Write the message

- Subject: imperative mood, at most 72 characters (aim for 50), no trailing period, type and scope per the convention, describing the change from the reader's point of view.
- Body, when the change isn't trivial, wrapped at 72 columns: what changed and why (not how), notable trade-offs, migration notes.
- Footers: `BREAKING CHANGE: ...` when it applies; issue references only when you actually know them (branch name, the user, the plan). Never invent issue numbers. Add any trailers the project or the user requires.

## 6. Confirm and commit

Show the plan: each commit with its files and full message. Commit after the user approves, or right away with `--yes`. One commit at a time: stage that commit's files, write the message to a temp file, run `git commit -F <file>`.

If a hook fails, read its output. Fix purely mechanical problems (formatter, lint autofix) and retry once; otherwise stop and report. Never use `--no-verify` unless the user explicitly asks for it.

`--amend` is allowed only when the last commit provably hasn't been pushed. Local remote-tracking refs can be stale, so refresh them first: `git fetch --quiet <remote>` (the branch's upstream remote, usually `origin`). If the fetch fails, refuse, because the remote state can't be established. After a successful fetch, refuse if `git branch -r --contains HEAD` prints anything. With no remote configured, nothing can have been pushed and amending is fine. When you refuse, explain why.

## 7. Finish

Show `git log --oneline -n <number of new commits>` and `git status -sb`. Don't push. When the branch is ready, mention `/bosun:ship`.
