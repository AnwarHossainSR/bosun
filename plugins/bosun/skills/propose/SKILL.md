---
name: propose
description: OpenSpec's name for /bosun:plan (propose a change for your approval).
argument-hint: "<what to build | GitHub issue #123 or URL> [--id change-id] [--solo|--crew] [--parallel N] [--classic] [--no-critique]"
disable-model-invocation: true
---

# bosun propose

Request: $ARGUMENTS

`/bosun:propose` is `/bosun:plan` under OpenSpec's name. Invoke the `bosun:plan` skill with this request as its arguments and follow it. Without the Skill tool: read `${CLAUDE_PLUGIN_ROOT}/skills/plan/SKILL.md` and follow it with this request; `${CLAUDE_PLUGIN_ROOT}` is the plugin root its paths start from.
