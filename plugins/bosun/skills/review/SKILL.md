---
name: review
description: Multi-agent code review of local changes - uncommitted work, staged changes, a branch against its base, or a commit range. Parallel reviewers each take a lens (correctness, spec, design, performance, tests, security), blocking findings are verified independently, and you get one de-duplicated report ranked by severity. --fix applies the confirmed fixes. Use before committing, before a PR, or after a build.
argument-hint: "[staged | working | <base>...<head> | <commit>] [--lenses correctness,tests,security,...] [--fix]"
---

# bosun review

Target: $ARGUMENTS

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors and numbers stay exact; warnings, destructive steps, ordered steps and questions get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

## 1. Resolve the target

- **Default**: everything on this branch that isn't in its base, plus uncommitted work. Base ref: `origin/<default branch>` if it exists, else the local default branch. Compute the merge base with `git merge-base HEAD <base ref>`; the diff is `git diff <merge-base>` (committed and uncommitted changes against the merge base), plus untracked files from `git ls-files --others --exclude-standard`.
- `staged`: `git diff --cached`. `working`: `git diff HEAD` plus untracked files. `A...B`: `git diff A...B`. A single commit: `git show <sha>`.

Show the `--stat`. If there's nothing to review, say so and stop.

## 2. Context

Commit messages in the range; the PR or plan task this belongs to (its acceptance criteria, if it's a bosun task); the OpenSpec change it implements, if any (a bosun board with `meta.openspec_change`, or files under `openspec/changes/` in the diff); CLAUDE.md conventions; which checks the project has.

## 3. Choose lenses and split the work

Unless `--lenses` is given:
- always `correctness`;
- `spec` when the work implements an OpenSpec change: give the reviewer the change's requirement blocks (`openspec/changes/<id>/specs/`) and ask it to check every scenario against the code and tests;
- `tests` when code changed;
- `security` when the diff touches auth, sessions, crypto, input parsing, queries, file or network I/O, deserialization, permissions, secrets or config, dependencies, CI or infrastructure;
- `design` for new modules, public APIs, or more than about 300 changed lines;
- `performance` for data access, loops over collections, hot paths, rendering;
- `accessibility` for UI changes; `api-compat` for public API, schema or config changes.

Large diffs (more than about 1,500 changed lines or 25 files): split by area (directory or module) and run one reviewer per lens and area, up to the parallel cap. Tell the user how many reviewers will run.

## 4. Review in parallel

In one message, spawn one `bosun:code-reviewer` per lens, and a `bosun:security-reviewer` in `diff` mode for the security lens. Each prompt contains: the exact diff command; how to read full files (the working tree, or `git show <head>:<path>`); the lens; the intent and context; and "report only issues introduced or made worse by this diff".

## 5. Merge and verify

- De-duplicate: the same location and the same root cause make one finding. Note which lenses agreed; agreement raises confidence.
- Verify: send every critical and high finding, and every medium finding with low confidence, to `bosun:verifier` (batch them into one or two verifier calls). Drop REFUTED findings; keep UNCERTAIN ones, labelled as such.

## 6. Report

Write `.bosun/reviews/<YYYY-MM-DD>-<slug>.md`, including the reviewed range and head sha. Show the user:
- the verdict: approve, approve with nits, or changes requested;
- findings by severity, each with `path:line`, the problem in one line, the failure scenario in one line, the fix, and its verification status;
- nits collapsed into one short list, and pre-existing issues listed separately.

Be specific and calm. No padding, no filler praise.

## 7. --fix

Apply fixes for confirmed critical, high and medium findings: trivial ones yourself, larger ones through `bosun:implementer`. Re-run the checks, then re-review only the changed areas with the lens that raised each finding. Don't commit unless the user asks (`/bosun:commit`).
