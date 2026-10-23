---
name: review
description: Multi-agent review of local changes (branch, staged, working tree, range, commit) through parallel lenses, with verified, de-duplicated findings; --fix applies them. Use before a commit or PR.
argument-hint: "[staged | working | <base>...<head> | <commit>] [--lenses correctness,tests,security,...] [--fix]"
---

# bosun review

Target: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Tokens:** first run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py"` `start` and keep its `mark`; the report ends with the lines `usage.py report --since <mark>` prints (this run, the session, the context left; plan limits are in `/usage`).

## 1. Resolve the target

- **Default**: everything on this branch that isn't in its base, plus uncommitted work. Base ref: `origin/<default branch>` if it exists, else the local default branch. Merge base: `git merge-base HEAD <base ref>`; the diff is `git diff <merge-base>` (committed and uncommitted changes against it), plus untracked files from `git ls-files --others --exclude-standard`.
- `staged`: `git diff --cached`. `working`: `git diff HEAD` plus untracked files. `A...B`: `git diff A...B`. A single commit: `git show <sha>`.

Show the `--stat`. Nothing to review (an empty stat and, for the default target and `working`, no untracked files from `git ls-files --others --exclude-standard`): say so and stop. Size = `--shortstat` plus the lines of untracked files in the target, leaving out lockfiles (`pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `bun.lock`, `Cargo.lock`, `poetry.lock`, `uv.lock`, `go.sum`, `composer.lock`, `Gemfile.lock`) and generated files: pathspecs such as `':!pnpm-lock.yaml'`, used in the reviewers' diff commands too. A changed lockfile goes to the security lens on its own, for supply-chain checks. Under about 300 changed lines, read the diff yourself to pick lenses. Larger: read only the stat and file list, never the whole diff (the reviewers read it, and a large diff would fill your context and delay them). Content triggers (`security` above all, also `performance` and `api-compat`) need the content: list matching files with the target's diff command plus `--name-only -G'<trigger regex>'` (untracked files: `grep -lE '<trigger regex>' <files>`), or open those files' diffs. Unsure whether `security` applies: include it.

## 2. Context

Commit messages in the range; the PR or plan task it belongs to (its acceptance criteria, for a bosun task); the OpenSpec change it implements, if any (a bosun board with `meta.openspec_change`, or files under an OpenSpec `changes/` directory in the diff); CLAUDE.md conventions; which checks the project has.

## 3. Choose lenses and split the work

Unless `--lenses` is given:
- always `correctness`;
- `spec` when the work implements an OpenSpec change: give the reviewer the path of the change's requirement blocks (`<openspec_dir>/changes/<id>/specs/`, `<openspec_dir>` = `planning.openspec_dir` in `.bosun/config.json`, default `openspec`) and ask it to check every scenario against the code and tests;
- `tests` when code changed;
- `security` when the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, deserialization, permissions, secrets or config, dependencies, CI or infrastructure;
- `design` for new modules, public APIs, or more than about 300 changed lines;
- `performance` for data access, loops over collections, hot paths, rendering;
- `accessibility` for UI changes; `api-compat` for public API, schema or config changes.

Split by size: under about 300 changed lines and at most 25 files, one `bosun:code-reviewer` takes every lens but security; up to about 1,500 lines and 25 files, one reviewer per lens; larger, or more than 25 files, split by area (directory or module) too, one reviewer per lens and area, up to the parallel cap. Tell the user how many reviewers will run.

## 4. Review in parallel

In one message, spawn the `bosun:code-reviewer` agents and, for the security lens, a `bosun:security-reviewer` in `diff` mode. Reviewers don't install dependencies or copy the repository: checks that need them use what is installed, or are reported as not run (if one matters, install once yourself and give every reviewer the path). Each prompt: the exact diff command; how to read full files (the working tree, or `git show <head>:<path>`); the lens or lenses; the intent and context (for a bosun task, its board path and id: the reviewer reads the brief); and "report only issues introduced or made worse by this diff".

## 5. Merge and verify

- De-duplicate: the same location and root cause make one finding; note which lenses agreed (agreement raises confidence).
- Verify: every critical and high finding, and every medium one with low confidence, goes to `bosun:verifier` (batched into one or two calls). Drop REFUTED findings; keep UNCERTAIN ones, labelled.

## 6. Report

Write `.bosun/reviews/<YYYY-MM-DD>-<slug>.md` with the reviewed range and head sha (`staged`: also the index tree from `git write-tree`), the findings and the pre-existing issues, in the same layout as what you show the user. Severity markers, used in every finding list: 🔴 critical · 🟠 high · 🟡 medium · 🔵 low · ⚪ nit; ✅ verified, ❔ uncertain.
- `## ✅ Approve`, `## 💬 Approve with nits` or `## ❌ Changes requested`, then the target, files and lines in one line;
- a one-row count table: `| 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ⚪ Nit |`;
- findings under `### 🔴 Critical`, `### 🟠 High` and so on, most severe first, each as `**<n>. <title>** · `path:line` · <lens> · ✅` (or ❔), then the problem and the failure scenario in a line each, then `**Fix:** ...`; omit empty severities;
- `### ⚪ Nits` as one short list; pre-existing issues as a count with the report path, plus one line for each critical or security one;
- last, the token lines (shown to the user, not saved in the report).

Be specific and calm; no padding, no filler praise.

## 7. --fix

Fixes land in the working tree, so every file a fix touches must hold exactly the reviewed code there. The default target and `working` always do. `staged`: the index must still be the reviewed one (`git write-tree` equals the tree recorded in the report) and the file must have no unstaged changes (not in `git diff --name-only`). A range or commit: its head must be `HEAD` (`git rev-parse <head>^{commit}` equals `git rev-parse HEAD`; `^{commit}` makes annotated tags compare as their commit) and the file must have no uncommitted changes (not in `git diff --name-only HEAD`). Otherwise change nothing: name the files that differ, and let the user check out the head, or commit or stash their edits, first.

Fix confirmed critical, high and medium findings: trivial ones yourself, larger ones through `bosun:implementer` in shared mode (no `isolation`, with the files it owns), so fixes land uncommitted in the working tree. Re-run the checks (long output into a log you tail: `set -o pipefail; log=$(mktemp); echo "log: $log"; <cmd> >"$log" 2>&1; code=$?; tail -n 40 "$log"; echo "exit $code"; (exit $code)`; if the tail doesn't show the cause, grep or read more of that log), then re-review only the changed areas with a `bosun:code-reviewer` (or `bosun:security-reviewer`) using the lens that raised each finding. Don't commit unless the user asks (`/bosun:commit`).
