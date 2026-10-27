---
name: review-pr
description: Review a GitHub pull request with the bosun lens panel; posts only text you approve. Use when given a PR number or URL.
argument-hint: "<pr-number | pr-url> [--post] [--lenses ...]"
---

# bosun review-pr

Pull request: $ARGUMENTS

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

**Tokens:** before anything else, run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/usage.py" start` and note the `mark:` it prints. At the end, run it with `report --since <mark>` and end your last message to the user with its lines as printed, never in a file you write or text you post. Run by another skill (build, ship): skip both, the outer one reports. If the script fails, say so in one line.

Needs the GitHub CLI: `gh auth status` must succeed; if not, explain `gh auth login` and stop. A PR in another repository: add `--repo <owner>/<repo>` to the gh commands.

## 1. Fetch

- `gh pr view <pr> --json number,title,body,author,baseRefName,headRefName,headRefOid,isDraft,isCrossRepository,headRepositoryOwner,additions,deletions,changedFiles,files,commits,labels,reviewDecision,statusCheckRollup,url`
- Size from the fields above (`additions`, `deletions`, `changedFiles`, `files`). Under about 300 changed lines, read the diff (`gh pr diff <pr>`) to pick lenses. Larger: don't read the whole diff (the reviewers do, and it would fill your context); after step 2, find content triggers for lenses (`security` above all) with `git diff <merge-base>...bosun/pr-<number> --name-only -G'<trigger regex>'` (fetch failed: grep the saved diff), or open those files' diffs. Unsure whether `security` applies: include it. A very large PR: tell the user and split the review by area.
- Existing review comments, so you don't repeat them, cut short because bots post long ones: `gh api repos/{owner}/{repo}/pulls/<number>/comments --paginate --jq '.[] | {path, line, user: .user.login, body: .body[0:300]}'`
- Issues linked in the description (`gh issue view <n>`), for intent.

## 2. Check out without touching the user's work

`<src>` is `origin` for a PR in this repository, else `https://github.com/<owner>/<repo>.git`. `git fetch <src> pull/<number>/head:bosun/pr-<number>` (prefix the refspec with `+` to update an existing branch), then `git worktree add .bosun/worktrees/pr-<number> bosun/pr-<number>`. For diffs, `git fetch <src> <baseRefName>` and at once take `git merge-base FETCH_HEAD bosun/pr-<number>` as the base (note its sha). Installs, tests, package scripts and builds run the PR's code, so before step 3 ask the user once whether the review may run it; recommend yes only for a same-repository PR (`isCrossRepository` false, `<src>` is `origin`) that changes no lockfile or manifest. With a yes, reviewers may run checks and you may install once as the review skill's step 4 says; without one, every reviewer and verifier prompt says "Run nothing from the worktree: read files only, and report checks as not run."

Fetch fails (a non-GitHub remote, missing permissions): `mkdir -p .bosun/reviews`, save `gh pr diff <pr>` to `.bosun/reviews/pr-<number>.diff`, and say the review had no full-file context.

## 3. Review

Read `${CLAUDE_PLUGIN_ROOT}/skills/review/SKILL.md` and follow its steps 3-5 with: diff `git diff <merge-base>...bosun/pr-<number> -- <its step 1 pathspecs>` (size from the same command's `--shortstat`; changed lockfiles to the security lens as its step 1 says) and full files from `.bosun/worktrees/pr-<number>` (fetch failed: the saved `.bosun/reviews/pr-<number>.diff` as the diff, and no full files); intent from the PR description and linked issues; CI status as context (failing checks deserve a note even if you don't diagnose them).

## 4. Draft

Save `.bosun/reviews/pr-<number>.md` in the review skill's step 6 layout (verdict heading, count table, findings by severity with their markers, each with `path:line`, problem, impact and fix), with lines in the PR's new version and each `path:line` a link to it at the head commit (`https://github.com/<owner>/<repo>/blob/<headRefOid>/<path>#L<line>`, a range `#L<start>-L<end>`), pre-existing issues listed in the draft itself (no local paths in posted text), questions, and specific praise only where earned. Show the draft to the user, and say how many findings can be posted on their lines (step 5).

## 5. Post (only after the user approves the final text)

Ask which way to post; recommend inline when any finding sits on a line the diff shows. Either way the posted text is the approved draft's, rearranged, never reworded. First check `gh pr view <number> --json headRefOid` still gives the reviewed sha; if not, the lines may have moved: tell the user and ask before posting.
- **Inline** (each finding on its line): one review through GitHub's "create a review for a pull request" REST endpoint, `gh api repos/<owner>/<repo>/pulls/<number>/reviews --method POST --input <file.json>`, with `commit_id` (the head sha), `event` `COMMENT`, `body`, and `comments`, each with `path`, `line`, `side` `RIGHT` (a range: also `start_line` and `start_side`) and `body`. Only lines inside the diff's hunks can take a comment. Each comment is one finding: `<marker> **<title>** · <lens> · <verification>`, then `**Problem:**`, `**Impact:**` and `**Fix:**`, then the reviewer's `suggestion` as a ```` ```suggestion ```` block (GitHub offers it as a one-click commit) only when it replaces exactly the commented lines, which you check in the worktree (fetch failed: in the saved diff); otherwise as a plain code block. The review `body` is the verdict heading, the count table, the findings without a diff line (in full, with their links), the nits, the questions and the pre-existing issues. GitHub rejects the request (a 422 names the field): check the current GitHub REST docs for that field, fix it once; a comment it still rejects moves into the body under its severity heading.
- **One comment** with everything: `gh pr review <number> --comment --body-file <file>`.
- `--approve` or `--request-changes` only if the user explicitly asks for that verdict.

## 6. Clean up

`git worktree remove .bosun/worktrees/pr-<number>`. Ask before deleting the local `bosun/pr-<number>` branch.
