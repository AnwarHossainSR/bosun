# bosun build: crew route

The build skill sends a crew run here (rolling pool). Loop until nothing is pending or in flight:

1. `TB next <board> --parallel <N> --json` (shared mode: add `--strict-files`): tasks whose deps are finished and whose files don't overlap work in flight, critical path first; keep each task's agent, kind, risk, spec_refs and security_sensitive for its gate. With `--only`, pass it on (`--only 1.1,2.3`): unlisted tasks then never take a slot, and the loop ends once the listed ones are finished. `stuck: true`: the skill's section 3.
2. Mark the tasks to start in one call: `TB set <board> <ids...> --status in_progress --assignee <agent>`.
3. Launch them **in one message**, one Agent call each: `subagent_type` = the task's agent (`bosun:implementer` unless it says otherwise); `isolation: "worktree"` for code tasks in worktree mode (not for report tasks or shared mode); `name` = the task id in lowercase with dots replaced (`t2-1` for 2.1), so you can message it later; `description` = "2.1 <short title>"; `prompt` = the template below.
4. Agents run in the background and you're notified as each finishes: process each result at once (the skill's section 2) and refill from step 1; don't wait for a whole wave. Foreground agents: process the batch when it returns, then continue.
5. About every 10 finished tasks, or after two failures in a row, spawn `bosun:monitor` with the board's absolute path and act on its recommendations.

Prompt template (keep it short; bosun agents get the project commands and output style from the startup hook):

```
Task <ID> of bosun plan "<plan title>". Read your brief first: <TB> brief <absolute board path> <ID>
Mode: <worktree: your own git worktree on your own branch, created from the work branch "<work_branch>". Commit there. Never push.
      | shared: the main checkout, with other agents. Edit only your owned files. Don't stage or commit.>
Main checkout (read-only reference): <absolute path>
<retries only: what went wrong last time and what to do differently>
```

An agent from outside bosun (the user's `.claude/agents/` or another plugin) gets neither the hook nor bosun's instructions: paste the brief and the project commands into its prompt and ask it to end with a `# BOSUN-RESULT` block (task, status, summary, branch, worktree, commit, spec_gaps).
