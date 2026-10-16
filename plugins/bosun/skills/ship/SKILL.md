---
name: ship
description: Ship the current branch - final quality gate (lint, typecheck, tests, build, quick review), push, and open a pull request with a structured description that follows the repository's PR template. Runs only when you invoke it, and asks before pushing.
argument-hint: "[--base <branch>] [--draft] [--no-review] [--title \"...\"]"
disable-model-invocation: true
---

# bosun ship

Arguments: $ARGUMENTS

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors and numbers stay exact; warnings, destructive steps, ordered steps and questions get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

## 1. Preconditions

- You're on a branch other than the base branch, and the working tree is clean. If it isn't clean, offer `/bosun:commit` and stop.
- A remote exists and `gh auth status` succeeds. If not, explain and stop; the user can still push by hand.
- Base branch: `--base`, else the bosun plan's `meta.base_branch`, else the repository's default branch. Run `git fetch origin <base>`. If the branch is behind `origin/<base>` or conflicts with it, tell the user and ask how to proceed (merge or rebase). Never rewrite pushed history without explicit approval.
- If an open PR already exists for this branch (`gh pr view --json url,state`), offer to update it by pushing instead of creating another.

## 2. Quality gate (run it yourself and report the real results)

Run the commands from `.bosun/config.json`, or the ones you detect: lint, typecheck, test, build. Any failure: stop, show it, and offer to fix it.

## 3. Quick review

Skip with `--no-review`, or when `.bosun/reviews/` already has a review of this exact HEAD sha. Otherwise run the `bosun:review` skill on `origin/<base>...HEAD` with lenses correctness and security. Critical or high findings: stop and report them.

## 4. Write the PR

- **Title**: the repository's convention (for example Conventional Commits), at most 72 characters.
- **Body**: if the repository has a PR template (`.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/*.md`, `docs/pull_request_template.md`, or `PULL_REQUEST_TEMPLATE.md`), keep its headings and fill them from the actual changes. Otherwise use: Summary, Changes, How to test, Risks and rollout, Linked issues. Draw on the commits, the bosun plan's SUMMARY.md if there is one, and the gate results.
- Don't invent issue numbers, test results, screenshots or metrics. Report only checks you actually ran.
- Write the body to a temp file.

## 5. Confirm, push, open

Show the base branch, title and body. After the user confirms:

1. `git push -u origin <branch>`
2. If an open PR already exists for this branch, don't create another: report its URL, and if the user wants its description refreshed, run `gh pr edit <number> --body-file <file>`. Otherwise run `gh pr create --base <base> --title "<title>" --body-file <file>` (add `--draft` if requested).

Print the PR URL and offer to check CI with `gh pr checks <number>`.
