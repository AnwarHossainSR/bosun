---
name: review-pr
description: Review a GitHub pull request with the bosun lens panel in a separate worktree; posts only after you approve the exact text. Use when given a PR number or URL.
argument-hint: "<pr-number | pr-url> [--post] [--lenses ...]"
---

# bosun review-pr

Pull request: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Tokens:** first run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py"` `start` and keep its `mark`; the report ends with the lines `usage.py report --since <mark>` prints (this run, the session, the context left; plan limits are in `/usage`).

Needs the GitHub CLI: `gh auth status` must succeed; if not, explain `gh auth login` and stop. A PR in another repository: add `--repo <owner>/<repo>` to the gh commands.

## 1. Fetch

- `gh pr view <pr> --json number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,additions,deletions,changedFiles,files,commits,labels,reviewDecision,statusCheckRollup,url`
- Size from the fields above (`additions`, `deletions`, `changedFiles`, `files`). Under about 300 changed lines, read the diff (`gh pr diff <pr>`) to pick lenses. Larger: don't read the whole diff (the reviewers do, and it would fill your context); after step 2, find content triggers for lenses (`security` above all) with `git diff <merge-base>...bosun/pr-<number> --name-only -G'<trigger regex>'` (fetch failed: grep the saved diff), or open those files' diffs. Unsure whether `security` applies: include it. A very large PR: tell the user and split the review by area.
- Existing review comments, so you don't repeat them: `gh api repos/{owner}/{repo}/pulls/<number>/comments --paginate`
- Issues linked in the description (`gh issue view <n>`), for intent.

## 2. Check out without touching the user's work

`<src>` is `origin` for a PR in this repository, else `https://github.com/<owner>/<repo>.git`. `git fetch <src> pull/<number>/head:bosun/pr-<number>` (prefix the refspec with `+` to update an existing branch), then `git worktree add .bosun/worktrees/pr-<number> bosun/pr-<number>`. For diffs, `git fetch <src> <baseRefName>` and at once take `git merge-base FETCH_HEAD bosun/pr-<number>` as the base (note its sha). Installing the PR's dependencies runs its install scripts, which is its code: for a PR from this repository's own branches, install once in the worktree if a check needs it; for a PR from a fork, ask first.

Fetch fails (a non-GitHub remote, missing permissions): `mkdir -p .bosun/reviews`, save `gh pr diff <pr>` to `.bosun/reviews/pr-<number>.diff`, and say the review had no full-file context.

## 3. Review

Read `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` and follow its steps 3-5 with: diff `git diff <merge-base>...bosun/pr-<number>` and full files from `.bosun/worktrees/pr-<number>` (fetch failed: the saved `.bosun/reviews/pr-<number>.diff` as the diff, and no full files); intent from the PR description and linked issues; CI status as context (failing checks deserve a note even if you don't diagnose them).

## 4. Draft

Save `.bosun/reviews/pr-<number>.md` in the review skill's step 6 layout (verdict heading, count table, findings by severity with their markers), with `path:line` in the PR's new version, open questions, and specific praise only where earned. Show the draft to the user, then the token lines; they stay out of anything posted.

## 5. Post (only after the user approves the final text)

- Default, one review comment with everything: `gh pr review <number> --comment --body-file <file>`.
- Inline comments on specific lines, only if the user wants them: GitHub's "create a review for a pull request" REST endpoint through `gh api ... --method POST --input <file.json>`. First check the current GitHub REST docs for the exact comment fields (path, body, and line/side or diff position), because the payload format matters. A comment GitHub rejects moves into the summary.
- `--approve` or `--request-changes` only if the user explicitly asks for that verdict.

## 6. Clean up

`git worktree remove .bosun/worktrees/pr-<number>`. Ask before deleting the local `bosun/pr-<number>` branch.
