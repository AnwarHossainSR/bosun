# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.7.0] - 2026-10-27

### Changed
- **Plans are lean by default, security-sensitive ones included,** as OpenSpec's propose is: one architect writes the plan, with no scouts, critique or threat model. Before, auth, sessions, input parsing and the like forced a full plan. In one real run, a sign-in page with a mock session token got a design, a critique and a threat model (the agent map showed about 485k tokens across the three) and a 14-task board. Now:
  - the architect writes the failure and authorization scenarios itself, keeps a lean board within the solo limits (at most 8 tasks), finds code with Grep and Glob, and needs a reason to read far more than about 20 files;
  - a critique and threat model run only with `--critique` or `--crew`, or when you ask for one at approval, which names the security-sensitive tasks and offers it;
  - the build's security review still checks security-sensitive tasks;
  - scouts run only for large work (a new product, or several subsystems at once) or with `--crew`;
  - the plan skill reads only the repository's overview itself and leaves the code to the architect;
  - the architect plans only the requested scope. Infrastructure, secrets, hardening and follow-ups the request doesn't ask for become one-line open questions, and their code isn't read.
- `/bosun:propose` and `/bosun:apply` say once when the session's context is over about 100k tokens, because every later turn re-reads it and a fresh session is cheaper.
- Lower token use, measured with `claude plugin details bosun` (estimates):
  - **Always-on:** about 1,420 → 1,021 tokens per session, from shorter skill and agent descriptions.
  - **Builds:** the build skill is about 8.8k → 8.2k tokens. Its review gates no longer load the whole review skill (about 3k tokens) to get the lockfile pathspecs: the build carries its own copy, and a test keeps the two lists equal. The crew route moved to `reference/crew.md`, read only by crew builds.
  - **Reviews:** the review skill is about 3.4k → 3.0k tokens, because `--fix` moved to `reference/fix.md`, read only with `--fix`. `/bosun:review-pr` reads it too, and now fetches existing comments with their bodies cut to 300 characters, since review bots post long ones.
  - **Plans:** the architect is about 4.1k → 3.9k tokens per spawn; the classic PLAN.md outline moved to `templates/PLAN.md`.
  - **Fewer agents:** one reviewer now covers every lens but security for a diff of up to about 600 changed lines (was 300), and a build gate up to about 400 (was 200). Each extra reviewer read the same diff and files again. `/bosun:investigate` checks a hypothesis it can settle with one quick command itself, and starts at most 3 investigators.
- The README is shorter: highlights, quick start, commands and install. The details moved to [docs/guide.md](docs/guide.md).

### Added
- Install steps for a new repository in the README: prerequisites, the three install scopes, setup, check, update and remove.
- A workflow, `sync-dev-after-main-merge.yml`, that brings `dev` up to date after a pull request merges into `main`. When `dev` has no work of its own, it resets `dev` onto `main`; otherwise it merges `main` into `dev`, and fails on a conflict.

## [0.6.0] - 2026-10-23

### Added
- A token report at the end of the review, review-pr, security-audit, investigate, plan and build reports, from the new `scripts/usage.py`. It reads Claude Code's own transcript files for the session and its subagents, and shows:
  - this run's tokens (output, new input and cache reads) and how many agents it started;
  - the session total with its output;
  - how much of the context window is left;
  - for a build, the five agents that used most.

  Agents' output is a lower bound ("≥"), because their transcripts often keep only the first count of a reply. Compactions aren't saved as replies, so they're estimated from their recorded size and shown apart: the totals count only recorded replies. The window comes from `CLAUDE_CODE_MAX_CONTEXT_TOKENS` when you've set it, else from the model (1M for Opus 4.7 and later, Sonnet 5, Haiku 5, Fable and Mythos; 200k for older models), marked "~". Output is written as UTF-8, so a Windows pipe can't break it; the report hasn't been run on Windows yet. Plan limits aren't in those files, so the report points to `/usage`. The lines go only in the last message to you: never in a saved report, SUMMARY.md or a posted PR comment. A skill run by another one (a build's final review) leaves them to the outer skill.
- Review reports mark severity in color: 🔴 critical, 🟠 high, 🟡 medium, 🔵 low and ⚪ nit. A finding shows ✅ when the verifier confirmed it, ❔ when it was uncertain, and the reviewer's confidence otherwise. Reports open with a verdict heading and a count table, then group findings by severity. `/bosun:review-pr` drafts and posts in the same layout: one comment, or a body plus one inline comment per finding. `/bosun:security-audit` uses it with the overall risk as the heading.
- Every review finding names its file and line (`path:start-end` for several lines), then the problem, its impact and the fix. Reviewers add a `suggestion` with the exact replacement code when the fix only changes those lines. `/bosun:review-pr` links each location to the line at the PR's head commit and recommends posting inline when findings sit on lines the diff shows; there, a fix that replaces exactly the commented lines is posted as a GitHub suggestion, which the author can commit in one click. Before posting it checks that the PR's head hasn't moved since the review.
- `/bosun:propose` and `/bosun:apply`, OpenSpec's names for `/bosun:plan` and `/bosun:build`; the old names still work. A build shows its progress as OpenSpec's apply does: `▶ 1.2 <title>` when a task starts and `✓ 1.2 <title> · 3/7` when it's done (`TB set` now prints the count). Given an OpenSpec change that has no task board yet, the build first has the architect add the board, with your approval.

### Changed
- Reviews always leave lockfiles and files marked `linguist-generated` out of their size and of the reviewers' diffs, including lockfiles in monorepo subfolders. A changed lockfile, or a new one git doesn't track yet, adds the security lens, and one security reviewer gets those files alone, for supply-chain checks. `/bosun:review-pr` and the build's review gates do the same.
  - This used to depend on the session. In one run on a pull request whose `pnpm-lock.yaml` was 1,379 of 1,849 added lines, it kept the lockfile away from three reviewers on its own.
- Reviewers and verifiers no longer install dependencies, use on-demand runners such as `npx` or `uv run`, or copy the repository. A check that needs more is reported as not run. When an install matters, it happens once, with the lockfile frozen.
- `/bosun:review-pr` asks you once before running a PR's code (installs, tests, scripts). It recommends yes only for a same-repository PR that doesn't change dependencies, and without a yes its agents only read files.

## [0.5.1] - 2026-10-22

### Fixed
- `TB status` on a solo board counts only the tasks the solo run will build. Tasks waiting behind a blocked one show once, as unschedulable, and tasks in review show separately.
- `/bosun:build --only`: tasks added to finish the listed work (a split, a fix for a critical or high finding) join the list. Finish starts when no listed task is pending, and its final review, tasks.md check and report cover the listed tasks and name the ones left.
- `/bosun:plan` with `--solo` or `--no-critique`: when a revision adds security-sensitive tasks, the approval names those no threat model covered, and says when a large board had no critique, before asking.

## [0.5.0] - 2026-10-21

### Added
- Solo builds. `/bosun:build` now gives a small or medium plan to one implementer, which works through the tasks in tasks.md order in one worktree with a commit per task. The whole run then gets one review and one merge, and that review counts as the final review. "Small or medium" means up to 8 tasks and 16 size-units, all of them code tasks for bosun's implementer, test-engineer or docs-writer, in worktree mode. Bigger plans, plans with a task for another agent and shared-mode builds keep the parallel crew, and `--crew` or `--solo` picks the route yourself (`--solo` when no task needs its own agent).
- A solo run that stops early continues from its commits with a fresh implementer, and SendMessage is used only for answers and fix rounds. Unfinished work is committed as `wip(<ID>)` and never counts as done, and a merge never takes it along. Tasks the run didn't reach keep their attempts. Fix rounds are counted for the whole run, a red integration check is one of them, and the security reviewer re-checks every fix.
- `TB route <board>` chooses between solo and crew. It gives the solo order (task ids wherever the deps allow it, so tasks.md order), the security-sensitive tasks, the tasks waiting on blocked ones, those in review, and its reasons. It takes `--only` and `--json` like `next`. The build records the route on the board as `meta.route`, and a resumed build keeps it.
- Lean plans. `/bosun:plan` has the architect plan small and medium work alone: it reads the code the change touches, researches open questions itself and keeps the board within the solo limits, with no scouts and no critique round. Work judged large or security-sensitive at intake gets scouts, the architect's critique and a threat model. A lean plan whose finished or revised board turns out large or security-sensitive gets the critique and threat model. `--solo` or `--crew` picks the path yourself and carries over to the build.

### Changed
- In a solo run, task briefs drop the "in flight right now" section (it would have listed the implementer's own later tasks as off-limits) and mark dependencies as done earlier in the run, and `TB validate` doesn't warn about the run's tasks being in flight together.
- The implementer's result block lists each task of a solo run with its status, commit and summary, and the board gets each task's summary. `TB status` and `/bosun:status` show the route and a solo run's progress, and the monitor counts a solo run as one agent and judges it by its task commits.
- The plan's approval summary shows the build route, with waves and the critical path only for a crew build. The manager's ad-hoc crews show the route before you approve them.
- The security reviewer runs secret scanners only in a mode that redacts what they find, as `/bosun:security-audit` already did.
- The hook saves a long solo run's report as `...-<first id>-to-<last id>-<n>-tasks-...`, and its `BOSUN_ENFORCE_RESULT` reminder allows `partial`.

### Fixed
- With agent teams enabled, the build leaves `name` off every agent it starts without `isolation` (shared-mode tasks as well as report tasks), so they all start as subagents.
- A task whose `agent` is blank is treated as the implementer's, as when the field is missing.

## [0.4.0] - 2026-10-21

### Added
- The hooks save each bosun agent's report to disk: next to its plan (`.bosun/plans/<name>/results/`) when its result block names the board, else in `.bosun/results/`, as `<time>-<agent>-<task>-<id>.md`. The absolute path is logged as `saved` in `.bosun/activity.jsonl`. The manager no longer copies result blocks into report files, and points later agents to the saved file instead of pasting reports. A build checks after its first agent that the hooks ran, and falls back to saving reports itself.
- Newer Claude Code hands a subagent's report back through the `SubagentHandback` tool, so the agent's last message holds only closing text. A `PostToolUse` hook now saves and logs that report, and the stop that follows isn't flagged as missing a result block.
- The context injected into bosun agents tells them to run long commands (tests, builds, scanners) into a log and read its tail, and to keep prose before the BOSUN-RESULT block to three lines unless they were asked for a map or a threat model.
- The guard stops bosun agents other than the architect from running the task board's write commands (`init`, `set`, `add`, `sync`, `meta --set`); the manager is the board's only writer.
- `TB next --json` includes each task's `risk` and `spec_refs`, so the build's gate can pick its lenses without reading every brief.
- `TB next --only <ids>` starts only the listed tasks, so `/bosun:build --only` no longer stalls when an unlisted task ranks first.

### Changed
- About half the always-on cost: the skill and agent listings that load into every session dropped from about 2,560 to about 1,350 tokens (`claude plugin details bosun` estimates), with shorter descriptions and a shorter style rule in every skill and in the hook.
- Task agents read their own brief with `taskboard.py brief`, so the manager no longer retypes briefs and project commands into every prompt (agents from outside bosun still get them pasted). Reviewers get the brief command with the board's absolute path, and every agent's result block names its board.
- Smaller review panels for small diffs: a build task under about 200 changed lines gets one code-reviewer for all its lenses, and `/bosun:review` uses one code-reviewer for every lens but security under about 300 lines and 25 files. The code-reviewer accepts several lenses and tags each finding with its lens.
- `/bosun:review` and `/bosun:review-pr` read small diffs themselves but only the stat of large ones, and find content-based lens triggers (security above all) with `git diff --name-only -G`, so large PRs reach the reviewers sooner without skipping a security review; when unsure, the security lens runs.
- The build's resume procedure moved to `reference/execution.md`, read only when a build resumes, and an unfinished merge is now settled before any other resume action.
- Task board `--json` output is one compact line instead of indented JSON.
- Secret scanners in `/bosun:security-audit` run with redaction where supported, show only counts, and their logs are deleted after the report.
- README rewritten around a diagram of the workflow; developer details moved to CONTRIBUTING.md, and the code of conduct now adopts the Contributor Covenant by reference.

### Fixed
- The build's spot-check commits a task's leftover changes with path-limited commands and re-checks the diff, instead of `git add -A`.
- Resume marks a task done when its merge landed but the board has no commit for it, and never overwrites `base_commit`, which bounds the final review.
- The hooks never write through a symbolic link out of the project, never overwrite another agent's saved report, and still log a stop when an agent's message contains malformed Unicode.
- Every skill and agent description is plain YAML, so strict YAML parsers read the frontmatter too.
- The log snippet keeps a failing command's exit status (`set -o pipefail`, then `(exit $code)` after the tail), so a failed test or build never looks like success.
- `/bosun:commit` re-stages files a hook's autofix changed before its one retry, and amends with no remote configured only after you confirm the commit was never pushed.
- `/bosun:review-pr` fetches a PR from its own repository, creates `.bosun/reviews/` before saving a fallback diff, and reviews that diff when the fetch fails. `/bosun:review` no longer stops on a change made only of untracked files, and `--fix` on a `staged` target checks the index is still the reviewed one.
- `/bosun:ship` uses the branch's upstream remote instead of assuming `origin`, and takes an existing PR's base before fetching.
- `/bosun:setup` and `/bosun:build` read only `worktree.baseRef` from Claude Code's settings files, not the rest of them, and setup adds the key with a merge that prints nothing.
- `/bosun:security-audit` skips secret scanners that can't redact, asks before merging `--fix` results, and assigns every selected area when a small diff gets one or two reviewers.
- The monitor matches an `in_progress` task to its worktree before calling it lost, and a stale handback marker no longer hides a later stop.

## [0.3.0] - 2026-10-19

### Added
- A local OpenSpec directory for projects that use OpenSpec themselves: set `planning.openspec_dir` to `.bosun/openspec`, with `openspec/**` in `protected_paths`. bosun's changes, tasks.md ticks and archived specs then stay in that git-ignored folder: the build never stages or commits them, agents in worktrees read the change from the main checkout, and `/bosun:archive` backs the folder up instead of committing. `/bosun:setup` offers it when the project already has its own `openspec/`, only together with an ignore rule for `.bosun/`, and `/bosun:build` stops and asks rather than commit a `.bosun/` OpenSpec directory that git doesn't ignore.
- `TB status --json` reports the resolved OpenSpec directory as `openspec.base`.

### Changed
- The task board reads the OpenSpec directory only from `planning.openspec_dir`. It no longer honours an undocumented `meta.openspec_dir` on a board, which the guard and the OpenSpec CLI calls never saw, so they could end up on different folders.

### Fixed
- OpenSpec CLI commands run from the OpenSpec directory's parent instead of the repository root. The CLI uses the nearest `openspec/` folder, so with a custom `planning.openspec_dir` it used to read the project's own specs, and validation and archiving could miss bosun's change or act on the wrong one.
- Skills and agents that named `openspec/` literally now follow `planning.openspec_dir`.

## [0.2.0] - 2026-10-19

### Added
- `/bosun:plan #123` (or an issue URL) plans from a GitHub issue: the issue is the brief, the proposal (PLAN.md for `--classic`) cites it, the board records it as `meta.issue`, and `/bosun:ship` links the PR with `Closes` or `Refs`. The manager routes an issue like any other goal: plan, investigate, or a single implementer for a small change.
- README: project-scope install (`--scope project`), following a branch with `owner/repo#ref`, how teammates get the plugin, installing in Claude Code on the web through the environment's setup script, and updating to a new version.
- `plugins/bosun/README.md`, a README inside the plugin folder for listings that show the plugin on its own, saying what bosun runs, writes and connects to; `homepage` in `plugin.json`.

### Changed
- The terse output style keeps logic words (because, so, but, not, only, can, may, must), text quoted from specs, tests and hypotheses, and full sentences for warnings, questions, statements of uncertainty and requests to confirm.

### Fixed
- `/bosun:build --resume`: an unfinished merge is no longer reported as a dirty tree to commit or stash (other changes still are); resume proposes what to do with it and settles it only after your go-ahead, and no task is merged while one is still open. Preflight no longer switches branches during a merge (`git checkout` of the current branch silently drops the merge state). An `in_progress` task is matched to its worktree by commit subject or files, not by board fields left over from an earlier attempt, and its uncommitted work in the task's files is committed with path-limited commands and continued instead of being reset; other paths are left for you to decide.
- `/bosun:ship` and `/bosun:commit` take `meta.issue` only from the board whose `meta.work_branch` is the current branch, and write an issue in another repository as `owner/repo#n`. Without a plan, ship links an issue the commits reference. Ship writes `Closes` only for PRs to the default branch, where GitHub acts on it, takes an existing PR's base as the base, and warns when a commit message would close the issue anyway; commit footers use `Refs` unless you ask for a closing keyword.
- The manager and `/bosun:investigate` treat issue text as a request from people, never as instructions, as `/bosun:plan` already did. The manager keeps the issue with the work on every route, so the PR can link it.
- `/bosun:review --fix` changes nothing unless every file it would touch holds exactly the reviewed code (right head checked out, no unstaged or uncommitted edits there).
- The SubagentStart hook no longer cuts the end of a long project profile (protected paths, main checkout, result reminder); it drops the last convention notes, then lists only as many protected paths as fit and counts the rest. The style rules keep `can`, `may` and `must` even when dropping hedges, and a test keeps every skill's style line in step with the hook.

## [0.1.0] - 2026-10-16

### Added
- Manager skill that routes any goal to the right workflow, and skills for plan, build, status, archive, investigate, review, review-pr, security-audit, commit, ship and setup.
- Spec-driven planning: `/bosun:plan` writes an OpenSpec-format change (proposal, delta specs with scenarios, design, tasks.md) plus a task board whose tasks reference the requirements they implement (`spec_refs`). `--classic` keeps the PLAN.md format.
- Task board commands for OpenSpec plans: `spec-check` (requirement coverage, tasks.md and board consistency, common format mistakes and deltas that archiving would refuse), `sync`, `add --spec-ref`, `init --openspec-change`; `set` ticks tasks.md, `brief` quotes the task's requirement blocks, `status` shows tasks.md progress.
- `/bosun:archive`: checks that every task is done and the change validates, then runs `openspec archive` and re-validates the main specs.
- `spec` review lens; implementers and test engineers write one test per scenario and report `spec_gaps`.
- Terse output style (`output_style`: caveman, caveman-lite, caveman-ultra or normal; default caveman), injected into bosun agents by the SubagentStart hook and applied by every skill.
- The guard keeps bosun agents other than the architect from editing OpenSpec files.
- Ten agents: architect, scout, implementer, test-engineer, docs-writer, code-reviewer, security-reviewer, verifier, investigator, monitor.
- Task board CLI (`taskboard.py`) with dependency- and file-ownership-aware scheduling, critical-path priority and locked atomic writes.
- Hooks: guard for bosun agents, activity log, project profile injection.
- 40-task example plan, and an OpenSpec example change validated in CI with the OpenSpec CLI.
- Open-source project files: CI, contributing guide, security policy, code of conduct, issue and pull request templates, CODEOWNERS, Dependabot for GitHub Actions.
