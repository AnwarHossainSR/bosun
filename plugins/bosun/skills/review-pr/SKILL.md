---
name: review-pr
description: Review a GitHub pull request with the bosun review panel. Fetches the PR (description, diff, CI status, existing comments), checks it out in a separate worktree without touching your working tree, runs lens reviewers in parallel, verifies findings, and drafts the review. Posts to GitHub only after you approve the exact text. Use when given a PR number or URL.
argument-hint: "<pr-number | pr-url> [--post] [--lenses ...]"
---

# bosun review-pr

Pull request: $ARGUMENTS

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, can, may, must); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

This needs the GitHub CLI: `gh auth status` must succeed. If it doesn't, explain how to authenticate (`gh auth login`) and stop. For a PR in another repository, add `--repo <owner>/<repo>` to the gh commands.

## 1. Fetch

- `gh pr view <pr> --json number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,additions,deletions,changedFiles,files,commits,labels,reviewDecision,statusCheckRollup,url`
- `gh pr diff <pr>`. Check the size first; for very large PRs tell the user and split the review by area.
- Existing review comments, so you don't repeat them: `gh api repos/{owner}/{repo}/pulls/<number>/comments --paginate`
- Linked issues mentioned in the description (`gh issue view <n>`), for intent.

## 2. Check out without touching the user's work

`git fetch origin pull/<number>/head:bosun/pr-<number>` (prefix the refspec with `+` to update an existing branch), then `git worktree add .bosun/worktrees/pr-<number> bosun/pr-<number>`. For diffs, `git fetch origin <baseRefName>` and take `git merge-base origin/<baseRefName> bosun/pr-<number>` as the base.

If the fetch fails (a non-GitHub remote, missing permissions), review from `gh pr diff` alone and say the review had no full-file context.

## 3. Review

Follow steps 3-5 of the `bosun:review` skill, with: diff `git diff <merge-base>...bosun/pr-<number>`; full files read from `.bosun/worktrees/pr-<number>`; intent from the PR description and linked issues; CI status as context (failing checks deserve a note even if you don't diagnose them).

## 4. Draft

Save `.bosun/reviews/pr-<number>.md` containing:
- a summary: verdict, the top issues, open questions, and specific praise only where it's earned;
- each finding with `path:line` (in the PR's new version), the problem, the failure scenario and the suggested fix.

Show the draft to the user.

## 5. Post (only after the user approves the final text)

- Default, one review comment with everything: `gh pr review <number> --comment --body-file <file>`.
- Inline comments on specific lines, only if the user wants them: use GitHub's "create a review for a pull request" REST endpoint through `gh api ... --method POST --input <file.json>`. First check the current GitHub REST docs for the exact comment fields (path, body, and line/side or diff position), because the payload format matters. If GitHub rejects a comment, move it into the summary.
- Use `--approve` or `--request-changes` only if the user explicitly asks for that verdict.

## 6. Clean up

`git worktree remove .bosun/worktrees/pr-<number>`. Ask before deleting the local `bosun/pr-<number>` branch.
