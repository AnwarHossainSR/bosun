---
name: apply
description: OpenSpec's name for /bosun:build (implement an approved change).
argument-hint: "[change-id|plan-slug|board-path] [--solo|--crew] [--parallel N] [--isolation worktree|shared] [--review task|batch|final] [--resume] [--only 1.1,2.3] [--dry-run]"
disable-model-invocation: true
---

# bosun apply

Arguments: $ARGUMENTS

`/bosun:apply` is `/bosun:build` under OpenSpec's name. Invoke the `bosun:build` skill with these arguments and follow it. Without the Skill tool: read `${CLAUDE_PLUGIN_ROOT}/skills/build/SKILL.md` and follow it with these arguments; `${CLAUDE_PLUGIN_ROOT}` is the plugin root its paths start from.
