---
name: plan
description: Plan a new product or multi-part feature, spec-driven. Clarifies requirements, maps the codebase with parallel scouts, has the architect write an OpenSpec change (proposal, delta specs with testable scenarios, design, tasks.md) plus a dependency-aware task board for parallel agents, gets it critiqued for architecture and security, validates it, and asks you to approve it. Use for anything bigger than a few files.
argument-hint: "<what to build> [--id change-id] [--parallel N] [--classic] [--no-critique]"
---

# bosun plan

Request: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`. Read `.bosun/config.json` if it exists. If it doesn't, mention `/bosun:setup` once and continue with the defaults: `max_parallel` 4, `planning.format` openspec, `planning.openspec_dir` `openspec`.

**Style:** follow `output_style` in the config (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors and numbers stay exact; warnings, destructive steps, ordered steps and questions get full sentences; never drop a fact or an uncertainty label. Specs, commits, PR text and docs stay normal prose. `normal` turns this off.

## 0. Format

- **openspec** (default): the plan is an OpenSpec change in `openspec/changes/<id>/`: proposal.md (why), `specs/<capability>/spec.md` (requirements with scenarios), design.md (how) and tasks.md (checklist). The board lives at `.bosun/plans/<id>/tasks.json`, linked by `meta.openspec_change`, with the same task ids as tasks.md.
- **plan** (`--classic`, or `planning.format: "plan"`): PLAN.md and tasks.json in `.bosun/plans/<slug>/`.
- The OpenSpec CLI is optional. Check `command -v openspec`. Without it, `TB spec-check` does the checking; mention once that `npm install -g @fission-ai/openspec` adds OpenSpec's own validation and is needed later for `/bosun:archive`, and that it sends anonymous usage statistics unless `OPENSPEC_TELEMETRY=0` is set. Don't install anything without asking.
- If the request names a change that already exists in `openspec/changes/<id>/`, skip to step 3 and use the architect's **board** mode.

## 1. Intake and clarify

- Restate the goal in two or three lines.
- Identify what would change the architecture or the spec: users and core flows; must-haves versus later; constraints (stack, hosting, budget, compliance); integrations; data and scale; auth model; deadline. Learn what you can from the repository (manifests, README, existing code, `openspec/specs/`) before asking.
- Ask at most five high-leverage questions in one batch, each with a recommended default (use AskUserQuestion when it's available). Skip questions that have an obvious default and state the default instead.
- Choose the change id unless `--id` was given: kebab-case and verb-led, such as `add-todo-api`. It must not exist under `openspec/changes/` or as `openspec/changes/archive/*-<id>`.

## 2. Recon (parallel)

- Existing codebase: spawn 1-3 `bosun:scout` agents in one message, each on a distinct question that matters for the goal (for example "how auth and sessions work", "data layer and migrations", "test setup and CI"). Include the goal so they know what to look for.
- Greenfield or empty repository: skip scouts, or send one to record the tooling that already exists.
- Research spikes that block the design (library choice, API capability): one scout per question, asking for a recommendation backed by sources it actually checked.

## 3. Design

Spawn `bosun:architect` in **design** mode with the format, the brief (goal, answers, defaults chosen, constraints), the scouts' summaries and key files, the change id, the absolute paths of the OpenSpec directory and the board, `max_parallel`, the project conventions, and whether the OpenSpec CLI is installed.

## 4. Validate

Run these yourself:
- `TB validate <board>` and `TB waves <board> --parallel <N>`;
- openspec format: `TB spec-check <board>`, and with the CLI `OPENSPEC_TELEMETRY=0 openspec validate <id> --strict --no-interactive` from the repository root.

On errors, re-spawn the architect in **revise** mode with the exact errors (at most two rounds), then validate again.

## 5. Critique (parallel; skip with --no-critique)

In one message spawn:
- `bosun:architect` in **critique** mode on the change (or PLAN.md) and the board;
- `bosun:security-reviewer` in **threat-model** mode on the proposal, specs and design (or PLAN.md).

Decide which changes to accept; check any factual claim you're unsure of. Apply the accepted changes with the architect in **revise** mode, then validate again.

## 6. Present and get approval

Show the user, concisely:
- the goal, the capabilities, and the key decisions, including anything marked `verify:`;
- per capability, the requirement names (one line each), so the user can review the contract without reading every file;
- task count by agent, waves and critical path from `TB waves`, and the first wave;
- top risks, assumptions and open questions;
- the paths: the change directory (proposal.md, specs/, design.md, tasks.md) and the board. Show `TB graph <board>` (a Mermaid diagram) only if asked.

Ask: approve, change something, or stop. The spec is the contract, so changes go back through the architect in **revise** mode and are validated again. On approval, offer to start `/bosun:build <id>`, or start it directly if the user already said to build. Never start building without approval. The change files stay uncommitted until the build commits them on its work branch.
