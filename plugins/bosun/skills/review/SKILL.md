---
name: review
description: Multi-agent review of local changes (branch, staged, working tree, range, commit) through parallel lenses, with verified, de-duplicated findings; --fix applies them. Use before a commit or PR.
argument-hint: "[staged | working | <base>...<head> | <commit>] [--lenses correctness,tests,security,...] [--fix]"
---

# bosun review

Target: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

## 1. Resolve the target

- **Default**: everything on this branch that isn't in its base, plus uncommitted work. Base ref: `origin/<default branch>` if it exists, else the local default branch. Merge base: `git merge-base HEAD <base ref>`; the diff is `git diff <merge-base>` (committed and uncommitted changes against it), plus untracked files from `git ls-files --others --exclude-standard`.
- `staged`: `git diff --cached`. `working`: `git diff HEAD` plus untracked files. `A...B`: `git diff A...B`. A single commit: `git show <sha>`.

Show the `--stat`. Nothing to review: say so and stop. Read only `--stat` and `--shortstat` yourself, never the whole diff: the reviewers read it, and a large diff would fill your context and delay them. Pick lenses from the file list; open a single file's diff only when its role isn't clear from the path.

## 2. Context

Commit messages in the range; the PR or plan task it belongs to (its acceptance criteria, for a bosun task); the OpenSpec change it implements, if any (a bosun board with `meta.openspec_change`, or files under an OpenSpec `changes/` directory in the diff); CLAUDE.md conventions; which checks the project has.

## 3. Choose lenses and split the work

Unless `--lenses` is given:
- always `correctness`;
- `spec` when the work implements an OpenSpec change: the reviewer gets the change's requirement blocks (`<openspec_dir>/changes/<id>/specs/`, `<openspec_dir>` = `planning.openspec_dir` in `.bosun/config.json`, default `openspec`) and checks every scenario against the code and tests;
- `tests` when code changed;
- `security` when the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, deserialization, permissions, secrets or config, dependencies, CI or infrastructure;
- `design` for new modules, public APIs, or more than about 300 changed lines;
- `performance` for data access, loops over collections, hot paths, rendering;
- `accessibility` for UI changes; `api-compat` for public API, schema or config changes.

Split by size: under about 300 changed lines, one `bosun:code-reviewer` takes every lens but security; up to about 1,500 lines, one reviewer per lens; larger (or more than 25 files), split by area (directory or module) too, one reviewer per lens and area, up to the parallel cap. Tell the user how many reviewers will run.

## 4. Review in parallel

In one message, spawn the `bosun:code-reviewer` agents and, for the security lens, a `bosun:security-reviewer` in `diff` mode. Each prompt: the exact diff command; how to read full files (the working tree, or `git show <head>:<path>`); the lens or lenses; the intent and context (for a bosun task, its board path and id: the reviewer reads the brief); and "report only issues introduced or made worse by this diff".

## 5. Merge and verify

- De-duplicate: the same location and root cause make one finding; note which lenses agreed (agreement raises confidence).
- Verify: every critical and high finding, and every medium one with low confidence, goes to `bosun:verifier` (batched into one or two calls). Drop REFUTED findings; keep UNCERTAIN ones, labelled.

## 6. Report

Write `.bosun/reviews/<YYYY-MM-DD>-<slug>.md` with the reviewed range and head sha, the findings and the pre-existing issues. Show the user:
- the verdict: approve, approve with nits, or changes requested;
- findings by severity, each with `path:line`, the problem and the failure scenario in a line each, the fix, and its verification status;
- nits collapsed into one short list; pre-existing issues only as a count with the report path.

Be specific and calm; no padding, no filler praise.

## 7. --fix

Fixes land in the working tree, so every file a fix touches must hold exactly the reviewed code there. The default target and `working` always do. `staged`: the file has no unstaged changes (not in `git diff --name-only`). A range or commit: its head must be `HEAD` (`git rev-parse <head>^{commit}` equals `git rev-parse HEAD`; `^{commit}` makes annotated tags compare as their commit) and the file has no uncommitted changes (not in `git diff --name-only HEAD`). Otherwise change nothing: name the files that differ, and let the user check out the head, or commit or stash their edits, first.

Fix confirmed critical, high and medium findings: trivial ones yourself, larger ones through `bosun:implementer` in shared mode (no `isolation`, with the files it owns), so fixes land uncommitted in the working tree. Re-run the checks (long output into a log you tail: `log=$(mktemp); <cmd> >"$log" 2>&1; echo "exit $?"; tail -n 40 "$log"`), then re-review only the changed areas with a `bosun:code-reviewer` (or `bosun:security-reviewer`) using the lens that raised each finding. Don't commit unless the user asks (`/bosun:commit`).
