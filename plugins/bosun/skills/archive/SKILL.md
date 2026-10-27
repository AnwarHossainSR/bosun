---
name: archive
description: Archive a finished OpenSpec change into the main specs, after checks and your confirmation.
argument-hint: "[change-id] [--yes]"
disable-model-invocation: true
---

# bosun archive

Arguments: $ARGUMENTS

TB = `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`. `<openspec_dir>` = `planning.openspec_dir` in `.bosun/config.json` (default `openspec`). Run every `openspec` command with `OPENSPEC_TELEMETRY=0`, from the OpenSpec directory's parent (repository root for `openspec`, `.bosun/` for `.bosun/openspec`): the CLI uses the nearest `openspec/` folder, so from elsewhere it could archive into the wrong specs. A **local** OpenSpec directory is one git ignores (`git check-ignore -q <openspec_dir>/changes` succeeds); git can neither show nor undo changes there, so the steps below back it up instead of committing.

**Style:** `output_style` in `.bosun/config.json` (default `caveman`): your prose and agent prompts terse, no filler; code, commands, paths, errors, numbers and quotes exact; keep logic words (because, so, but, not, only, can, may, must); full sentences for warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty; never drop a fact or an uncertainty label. Commits, PR text, docs and specs: normal prose. `normal` turns it off.

## 1. Resolve the change

The argument; else `meta.openspec_change` of the latest board (`TB latest`, then `TB meta <board>`); else the only directory under `<openspec_dir>/changes/` other than `archive/`. Board: `.bosun/plans/<id>/tasks.json` when it exists. Already under `<openspec_dir>/changes/archive/`: say so and stop.

## 2. Preconditions (stop and report anything red)

- **OpenSpec CLI:** `command -v openspec`. bosun doesn't reimplement merging deltas into the main specs. Missing: explain that `npm install -g @fission-ai/openspec` installs it (it sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0`), and stop.
- **Spec check:** with a board, `TB spec-check <board>` reports no errors.
- **Every task done:** `openspec archive --yes` doesn't stop on unticked tasks, so list every unticked tasks.md line yourself. Tasks the board marks `skipped`: ask whether to drop those lines from the change (architect in revise mode) or finish them first. Never tick a task that isn't done.
- **Validation:** `openspec validate <id> --strict --no-interactive` passes.
- **Git:** not on the default branch (archive on the work branch so the result goes through review), and the working tree is clean apart from `.bosun/`. Local OpenSpec directory: no git requirement; instead, just before step 4, copy it to `.bosun/backups/openspec-<YYYYMMDD-HHMMSS>/` (`cp -R`) and say where the copy is.

## 3. Preview and confirm

Show the capabilities and how many requirements each delta adds, modifies, removes and renames, the archive destination (`<openspec_dir>/changes/archive/<YYYY-MM-DD>-<id>/`), and the current branch (local directory: the backup path instead). Ask to proceed unless `--yes` was given.

## 4. Archive and verify

1. `openspec archive <id> --yes`, and read the output. "Aborted" means nothing changed: report its reason and stop.
2. `openspec validate --specs --strict --no-interactive` must pass.
3. Show `git status --short` and `git diff --stat`: the change moved to the archive and the main specs under `<openspec_dir>/specs/` changed. Local directory: git shows nothing, so list `<openspec_dir>/changes/archive/` and the files under `<openspec_dir>/specs/` instead.

## 5. Commit

After the user confirms (or at once with `--yes`): `git add -A -- <openspec_dir>/`, then commit in the repository's convention, for example `docs(spec): archive <id>`. Don't push; mention `/bosun:ship`. Anything in step 4 failed: leave the changes uncommitted, show them, let the user decide. To undo an archive: `git restore --staged --worktree -- <openspec_dir>/`, then delete the untracked paths `git status --short -- <openspec_dir>/` still lists (the archive copy and any newly created main specs). Confirm with the user before deleting anything.

Local OpenSpec directory: nothing to commit. To undo an archive, replace `<openspec_dir>` with the backup from step 2, after the user confirms.
