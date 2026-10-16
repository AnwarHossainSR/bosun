# OpenSpec example: todo API

A small spec-driven plan in the layout `/bosun:plan` produces:

```text
openspec/config.yaml                          OpenSpec project config
openspec/changes/add-todo-api/
  .openspec.yaml                              schema and creation date
  proposal.md                                 why, what changes, capabilities, impact
  specs/user-accounts/spec.md                 3 ADDED requirements with scenarios
  specs/todo-items/spec.md                    5 ADDED requirements with scenarios
  design.md                                   decisions, risks, migration plan
  tasks.md                                    8 tasks in 4 groups
.bosun/plans/add-todo-api/tasks.json          the board: same task ids, deps, file ownership, spec_refs
```

There is no application code here; the plan is the example. Try the checks from the repository root:

```bash
TB="python3 plugins/bosun/scripts/taskboard.py"
B=examples/openspec-todo-api/.bosun/plans/add-todo-api/tasks.json
$TB spec-check $B            # requirement coverage, tasks.md vs board, format checks
$TB waves $B --parallel 3    # 6 waves
$TB brief $B 3.1             # the brief an implementer gets, with its requirements quoted

# with the OpenSpec CLI installed (npm install -g @fission-ai/openspec)
cd examples/openspec-todo-api && OPENSPEC_TELEMETRY=0 openspec validate add-todo-api --strict --no-interactive
```

`set --status done` would tick tasks.md in this folder, so try that on a copy.
