---
name: ship
description: Final gate (lint, types, tests, build, quick review), push, and a PR from the repository's template. Runs only when you invoke it; asks before pushing.
argument-hint: "[--base <branch>] [--draft] [--no-review] [--title \"...\"]"
disable-model-invocation: true
---

# bosun ship

Arguments: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

## 1. Preconditions

- On a branch other than the base branch, with a clean working tree. Not clean: offer `/bosun:commit` and stop.
- A remote exists and `gh auth status` succeeds. If not, explain and stop; the user can still push by hand.
- The bosun plan, if any, is the board (`.bosun/plans/<name>/tasks.json`) whose `meta.work_branch` is the current branch. Ignore other boards: their SUMMARY.md, base branch and issue belong to other work.
- Base branch: `--base`, else the plan's `meta.base_branch`, else the repository's default branch. `git fetch origin <base>`. Behind `origin/<base>` or conflicting with it: tell the user and ask how to proceed (merge or rebase). Never rewrite pushed history without explicit approval.
- An open PR already exists for this branch (`gh pr view --json url,state,baseRefName`): offer to update it by pushing instead of creating another. Its `baseRefName` is then the base for everything below; tell the user if it differs from `--base` or `meta.base_branch`.

## 2. Quality gate (run it yourself, report the real results)

The commands from `.bosun/config.json`, or the ones you detect: lint, typecheck, test, build, each into a log you tail (`log=$(mktemp); <cmd> >"$log" 2>&1; echo "exit $?"; tail -n 40 "$log"`). Any failure: stop, show it, offer to fix it.

## 3. Quick review

Skip with `--no-review`, or when `.bosun/reviews/` already has a review of this exact HEAD sha. Otherwise run the `bosun:review` skill on `origin/<base>...HEAD` with lenses correctness and security. Critical or high findings: stop and report them.

## 4. Write the PR

- **Title**: the repository's convention (Conventional Commits, for example), 72 characters at most.
- **Body**: a PR template (`.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/*.md`, `docs/pull_request_template.md`, or `PULL_REQUEST_TEMPLATE.md`): keep its headings and fill them from the actual changes. Otherwise: Summary, Changes, How to test, Risks and rollout, Linked issues. Draw on the commits, the plan's SUMMARY.md if there is one, and the gate results.
- **Issue link**: the plan's `meta.issue`, or without a plan an issue the commits reference or the user names; `#<n>` in this repository, `<owner>/<repo>#<n>` in another. `Closes` when the work delivers everything the issue asks for and the PR targets the default branch, otherwise `Refs`. GitHub acts on closing keywords in a PR body only for PRs to the default branch, but also on closing keywords in commit messages once those commits reach the default branch. So check `git log --format=%B origin/<base>..HEAD` for close, closes, closed, fix, fixes, fixed, resolve, resolves or resolved followed by the issue before you tell the user which keyword you used and whether merging will close the issue. A commit that would close it anyway: say so; rewording it rewrites history, so only offer it.
- Don't invent issue numbers, test results, screenshots or metrics; report only checks you actually ran.
- Write the body to a temp file.

## 5. Confirm, push, open

Show the base branch, title and body. After the user confirms:

1. `git push -u origin <branch>`
2. An open PR exists for this branch: don't create another; report its URL, and if the user wants its description refreshed, `gh pr edit <number> --body-file <file>`. Otherwise `gh pr create --base <base> --title "<title>" --body-file <file>` (`--draft` if requested).

Print the PR URL and offer to check CI with `gh pr checks <number>`.
