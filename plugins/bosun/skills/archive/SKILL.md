---
name: archive
description: Archive a finished OpenSpec change. Checks that every task in tasks.md is done and the change validates, runs `openspec archive` to merge its requirements into the main specs, re-validates them, and commits the result after you confirm (a git-ignored OpenSpec directory is backed up instead). Runs only when you invoke it.
argument-hint: "[change-id] [--yes]"
disable-model-invocation: true
---

# bosun archive

Arguments: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`. `<openspec_dir>` is `planning.openspec_dir` in `.bosun/config.json` (default `openspec`). Run every `openspec` command with `OPENSPEC_TELEMETRY=0` set, from the OpenSpec directory's parent (the repository root for `openspec`, `.bosun/` for `.bosun/openspec`): the CLI uses the nearest `openspec/` folder, so from anywhere else it could archive into the wrong specs. A **local** OpenSpec directory is one git ignores (`git check-ignore -q <openspec_dir>/changes` succeeds). Git can neither show nor undo changes there, so the steps below back it up instead of committing.

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, can, may, must); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

## 1. Resolve the change

The argument; else `meta.openspec_change` of the latest board (`TB latest`, then `TB meta <board>`); else the only directory under `<openspec_dir>/changes/` other than `archive/`. Board: `.bosun/plans/<id>/tasks.json` when it exists. If the change is already under `<openspec_dir>/changes/archive/`, say so and stop.

## 2. Preconditions (stop and report anything red)

- **OpenSpec CLI.** `command -v openspec`. bosun doesn't reimplement merging deltas into the main specs. Without the CLI, explain that `npm install -g @fission-ai/openspec` installs it (it sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0`), and stop.
- **Spec check.** With a board: `TB spec-check <board>` reports no errors.
- **Every task done.** `openspec archive --yes` does not stop on unticked tasks, so check tasks.md yourself: list every unticked line. For tasks the board marks `skipped`, ask whether to drop those lines from the change (architect in revise mode) or finish them first. Never tick a task that isn't done.
- **Validation.** `openspec validate <id> --strict --no-interactive` passes.
- **Git.** Not on the default branch (archive on the work branch so the result goes through review), and the working tree is clean apart from `.bosun/`. Local OpenSpec directory: no git requirement; instead, just before step 4, copy it to `.bosun/backups/openspec-<YYYYMMDD-HHMMSS>/` (`cp -R`) and say where the copy is.

## 3. Preview and confirm

Show the capabilities and how many requirements each delta adds, modifies, removes and renames, the archive destination (`<openspec_dir>/changes/archive/<YYYY-MM-DD>-<id>/`), and the current branch (for a local directory, the backup path instead). Ask to proceed unless `--yes` was given.

## 4. Archive and verify

1. `openspec archive <id> --yes`. Read the output. If it prints "Aborted", nothing changed: report its reason and stop.
2. `openspec validate --specs --strict --no-interactive` must pass.
3. Show `git status --short` and `git diff --stat`: the change moved to the archive and the main specs under `<openspec_dir>/specs/` changed. For a local directory git shows nothing, so list `<openspec_dir>/changes/archive/` and the files under `<openspec_dir>/specs/` instead.

## 5. Commit

After the user confirms (or right away with `--yes`): `git add -A -- <openspec_dir>/`, then commit with the repository's convention, for example `docs(spec): archive <id>`. Don't push; mention `/bosun:ship`. If anything in step 4 failed, leave the changes uncommitted, show them, and let the user decide. To undo an archive: `git restore --staged --worktree -- <openspec_dir>/`, then delete the untracked paths that `git status --short -- <openspec_dir>/` still lists (the archive copy and any newly created main specs). Confirm with the user before deleting anything.

Local OpenSpec directory: there is nothing to commit. To undo an archive, replace `<openspec_dir>` with the backup from step 2, after the user confirms.
