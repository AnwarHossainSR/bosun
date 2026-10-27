---
name: review
description: Multi-lens review of local changes (branch, staged, working tree, range, commit) with verified findings; --fix applies them. Use before a commit or PR.
argument-hint: "[staged | working | <base>...<head> | <commit>] [--lenses correctness,tests,security,...] [--fix]"
---

# bosun review

Target: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Tokens:** before anything else, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py" start` and note the `mark:` it prints. At the end, run it with `report --since <mark>` and end your last message to the user (with `--fix`: after step 7) with its lines as printed, never in a file you write or text you post. Run by another skill (build, ship): skip both, the outer one reports. If the script fails, say so in one line.

## 1. Resolve the target

- **Default**: everything on this branch that isn't in its base, plus uncommitted work. Base ref: `origin/<default branch>` if it exists, else the local default branch. Merge base: `git merge-base HEAD <base ref>`; the diff is `git diff <merge-base>` (committed and uncommitted changes against it), plus untracked files from `git ls-files --others --exclude-standard`.
- `staged`: `git diff --cached`. `working`: `git diff HEAD` plus untracked files. `A...B`: `git diff A...B`. A single commit: `git show <sha>`.

Show the `--stat`. Nothing to review (an empty stat and, for the default target and `working`, no untracked files from `git ls-files --others --exclude-standard`): say so and stop. Lockfiles and files the repository marks generated (`linguist-generated`; never migrations, snapshots, schemas or type declarations) stay out of the size and of every reviewer's diff, through these pathspecs, last and after `--` (options first): `':(exclude,glob,top)**/*.lock' ':(exclude,glob,top)**/*-lock.yaml' ':(exclude,glob,top)**/package-lock.json' ':(exclude,glob,top)**/npm-shrinkwrap.json' ':(exclude,glob,top)**/bun.lockb' ':(exclude,glob,top)**/go.sum' ':(exclude,top,attr:linguist-generated)' ':(exclude,top,attr:linguist-generated=true)'`. Size = `--shortstat` with them plus the lines of untracked files they keep (`git ls-files --others --exclude-standard -- <pathspecs>`). Changed lockfiles (the same names with `:(glob,top)` and `--name-only`; the default target and `working`: also untracked ones, `git ls-files --others --exclude-standard -- <those names>`): add the security lens, and give one security-reviewer a second diff command with only those files (untracked ones: their paths, to read in full), for supply-chain checks; name excluded generated files in the prompts. Under about 300 changed lines, read the diff yourself to pick lenses. Larger: read only the stat and file list, never the whole diff (the reviewers read it, and a large diff would fill your context and delay them). Content triggers (`security` above all, also `performance` and `api-compat`) need the content: list matching files with the target's diff command plus `--name-only -G'<trigger regex>'` (untracked files: `grep -lE '<trigger regex>' <files>`), or open those files' diffs. Unsure whether `security` applies: include it.

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

Split by size: under about 600 changed lines and at most 25 files, one `bosun:code-reviewer` takes every lens but security (each extra reviewer reads the same diff and files again); up to about 1,500 lines and 25 files, one reviewer per lens; larger, or more than 25 files, split by area (directory or module) too, one reviewer per lens and area, up to the parallel cap. Tell the user how many reviewers will run.

## 4. Review in parallel

In one message, spawn the `bosun:code-reviewer` agents and, for the security lens, a `bosun:security-reviewer` in `diff` mode. Reviewers and verifiers don't install dependencies or copy the repository (on-demand runners such as `npx`, `bunx`, `pnpm dlx` and `uv run` install too): checks use what is installed, or are reported as not run. If one matters, install once yourself with the lockfile frozen (`npm ci`, `pnpm install --frozen-lockfile`, `yarn install --immutable`, `uv sync --locked`) and check `git status --porcelain` didn't change (review-pr: only as its step 2 allows). Each prompt says so, and gives: the exact diff command; how to read full files (the working tree, or `git show <head>:<path>`); the lens or lenses; the intent and context (for a bosun task, its board path and id: the reviewer reads the brief); and "report only issues introduced or made worse by this diff".

## 5. Merge and verify

- De-duplicate: the same location and root cause make one finding; note which lenses agreed (agreement raises confidence).
- Verify every critical and high finding, and every medium one with low confidence, except those the reviewer gave high confidence (it ran or traced them end to end). One that a single file read or command settles: check it yourself. The rest go to `bosun:verifier` in one call (two for many). Drop REFUTED findings; keep UNCERTAIN ones, labelled.

## 6. Report

Write `.bosun/reviews/<YYYY-MM-DD>-<slug>.md` in the layout below, with a line under the heading for the range, the full head sha and (`staged`) the index tree from `git write-tree`, and every pre-existing issue under `### Pre-existing`. Show the user the same, with pre-existing issues as a count plus the report path. Markers: 🔴 critical · 🟠 high · 🟡 medium · 🔵 low · ⚪ nit; verification: ✅ the verifier CONFIRMED it, ❔ it was UNCERTAIN, else the reviewer's confidence (`high`, `medium` or `low` confidence), never ✅ for one the verifier didn't check.
- `## ✅ Approve`, `## 💬 Approve with nits` or `## ❌ Changes requested`, then the target, files and lines in one line;
- a one-row count table: `| 🔴 Critical | 🟠 High | 🟡 Medium | 🔵 Low | ⚪ Nit |`;
- findings under `### 🔴 Critical`, `### 🟠 High` and so on, most severe first (omit empty severities), each as `**<n>. <title>** · `path:line` · <lens> · <verification>` (a range: `path:start-end`, at the head revision), then:
  - `**Problem:**` what is wrong, quoting the line or lines;
  - `**Impact:**` the failure scenario: which input or state leads to which wrong result;
  - `**Fix:**` the specific change, then the reviewer's `suggestion`, if it gave one, as a fenced code block in the file's language: the replacement for exactly those lines;
- `### ⚪ Nits`: one line each, `path:line` and the change;
- `### ❓ Questions`: what the reviewers couldn't settle, with `path:line` where there is one;
- pre-existing issues, each as `path:line`, the problem and the fix in one line (shown as a count with the report path, plus that line for each critical or security one).

Be specific and calm; no padding, no filler praise.

## 7. --fix

Only with `--fix`: read `${CLAUDE_PLUGIN_ROOT}/skills/review/reference/fix.md` and follow it.
