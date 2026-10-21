---
name: review-pr
description: Review a GitHub pull request with the bosun lens panel in a separate worktree; posts only after you approve the exact text. Use when given a PR number or URL.
argument-hint: "<pr-number | pr-url> [--post] [--lenses ...]"
---

# bosun review-pr

Pull request: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

Needs the GitHub CLI: `gh auth status` must succeed; if not, explain `gh auth login` and stop. A PR in another repository: add `--repo <owner>/<repo>` to the gh commands.

## 1. Fetch

- `gh pr view <pr> --json number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,additions,deletions,changedFiles,files,commits,labels,reviewDecision,statusCheckRollup,url`
- Size from the fields above (`additions`, `deletions`, `changedFiles`, `files`). Don't read the whole diff yourself: the reviewers do, and a large one would fill your context. A very large PR: tell the user and split the review by area.
- Existing review comments, so you don't repeat them: `gh api repos/{owner}/{repo}/pulls/<number>/comments --paginate`
- Issues linked in the description (`gh issue view <n>`), for intent.

## 2. Check out without touching the user's work

`git fetch origin pull/<number>/head:bosun/pr-<number>` (prefix the refspec with `+` to update an existing branch), then `git worktree add .bosun/worktrees/pr-<number> bosun/pr-<number>`. For diffs, `git fetch origin <baseRefName>` and take `git merge-base origin/<baseRefName> bosun/pr-<number>` as the base.

Fetch fails (a non-GitHub remote, missing permissions): save `gh pr diff <pr>` to `.bosun/reviews/pr-<number>.diff`, give reviewers that path, and say the review had no full-file context.

## 3. Review

Read `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` and follow its steps 3-5 with: diff `git diff <merge-base>...bosun/pr-<number>`; full files from `.bosun/worktrees/pr-<number>`; intent from the PR description and linked issues; CI status as context (failing checks deserve a note even if you don't diagnose them).

## 4. Draft

Save `.bosun/reviews/pr-<number>.md`: a summary (verdict, top issues, open questions, specific praise only where earned), then each finding with `path:line` (in the PR's new version), the problem, the failure scenario and the suggested fix. Show the draft to the user.

## 5. Post (only after the user approves the final text)

- Default, one review comment with everything: `gh pr review <number> --comment --body-file <file>`.
- Inline comments on specific lines, only if the user wants them: GitHub's "create a review for a pull request" REST endpoint through `gh api ... --method POST --input <file.json>`. First check the current GitHub REST docs for the exact comment fields (path, body, and line/side or diff position), because the payload format matters. A comment GitHub rejects moves into the summary.
- `--approve` or `--request-changes` only if the user explicitly asks for that verdict.

## 6. Clean up

`git worktree remove .bosun/worktrees/pr-<number>`. Ask before deleting the local `bosun/pr-<number>` branch.
