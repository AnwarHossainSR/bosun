---
name: plan
description: Plan a new product or multi-part feature with a crew. Clarifies requirements, maps the codebase with parallel scouts, has the architect write PLAN.md and a dependency-aware task board (tasks.json) sized for parallel agents, gets the plan critiqued for architecture and security, and asks you to approve it. Use for anything bigger than a few files.
argument-hint: "<what to build> [--slug name] [--parallel N] [--no-critique]"
---

# bosun plan

Request: $ARGUMENTS

TB means `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/taskboard.py"`. Read `.bosun/config.json` if it exists. If it doesn't, mention `/bosun:setup` once and continue with defaults (max_parallel 4).

## 1. Intake and clarify

- Restate the goal in two or three lines.
- Identify what would change the architecture or scope: users and core flows; must-haves versus later; constraints (stack, hosting, budget, compliance); integrations; data and scale; auth model; deadline. Learn what you can from the repository (manifests, README, existing code) before asking.
- Ask at most five high-leverage questions in one batch, each with a recommended default (use AskUserQuestion when it's available). Skip questions that have an obvious default and state the default instead.
- Choose a slug (lowercase, dashes) unless `--slug` was given. Plan directory: `.bosun/plans/<slug>/`.

## 2. Recon (parallel)

- Existing codebase: spawn 1-3 `bosun:scout` agents in one message, each on a distinct question that matters for the goal (for example "how auth and sessions work", "data layer and migrations", "test setup and CI"). Include the goal so they know what to look for.
- Greenfield or empty repository: skip scouts, or send one to record the tooling that already exists.
- Research spikes that block the design (library choice, API capability): one scout per question, asking for a recommendation backed by sources it actually checked.

## 3. Design

Spawn `bosun:architect` in **design** mode with: the brief (goal, answers, defaults chosen, constraints), the scouts' summaries and key files, the absolute plan directory, `max_parallel`, and the project conventions. It writes PLAN.md and tasks.json.

## 4. Validate

Run `TB validate <dir>/tasks.json` and `TB waves <dir>/tasks.json --parallel <N>` yourself. On errors, re-spawn the architect in **revise** mode with the exact errors (at most two rounds), then validate again.

## 5. Critique (parallel; skip with --no-critique)

In one message spawn:
- `bosun:architect` in **critique** mode on PLAN.md and tasks.json;
- `bosun:security-reviewer` in **threat-model** mode on the same files.

Decide which changes to accept; check any factual claim you're unsure of. Apply the accepted changes with the architect in **revise** mode, then validate again.

## 6. Present and get approval

Show the user, concisely:
- the goal and key decisions, including anything marked `verify:`;
- task count by agent, waves and critical path from `TB waves`, and the first wave;
- top risks, assumptions and open questions;
- the plan path. Show `TB graph <board>` (a Mermaid diagram) only if asked.

Ask: approve, change something, or stop. On approval, offer to start `/bosun:build <slug>`, or start it directly if the user already said to build. Never start building without approval.
