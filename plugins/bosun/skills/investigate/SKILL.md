---
name: investigate
description: Root-cause a bug, failing or flaky test, incident, performance regression, or "why does X happen" with parallel investigators testing competing hypotheses, an independent verification pass, and a written report with evidence, fix options and a regression test. Can implement the fix test-first. Use for debugging and incident analysis.
argument-hint: "<symptom, error message, failing test or issue link> [--fix]"
---

# bosun investigate

Problem: $ARGUMENTS

**Style:** follow `output_style` in `.bosun/config.json` (default `caveman`): your own prose and agent prompts are terse fragments without filler; code, commands, paths, errors, numbers and quoted text stay exact; keep logic words (because, so, but, not, only, may); warnings, destructive steps, ordered steps, questions, requests to confirm and statements of uncertainty get full sentences; never drop a fact or an uncertainty label. Commits, PR text, docs and specs stay normal prose. `normal` turns this off.

## 1. Frame the problem

Collect what already exists before asking: error text and stack traces, the failing test or command, logs, the issue (`gh issue view <n>` for a GitHub issue), recent changes (`git log --oneline -20`, `git log --since="2 weeks ago" -- <suspect paths>`). Write down: expected versus actual behavior; where (environment, versions); since when (last known good commit or release); how often (always, intermittent, under load); and the blast radius. Ask the user only for what you can't find, and don't stall: start with what you have.

## 2. Reproduce

If it's cheap, reproduce it yourself by running the failing test or command. For a flaky failure, run it repeatedly (10-20 times) to measure the failure rate. Record the exact repro. A reliable repro is the most valuable artifact of the investigation.

## 3. Recon (optional)

In an unfamiliar area, spawn 1-2 `bosun:scout` agents in parallel to map the code path and the recent changes around it.

## 4. Hypotheses

List 2-5 distinct, falsifiable hypotheses, ranked by likelihood and by how cheap they are to test. Include at least one "boring" hypothesis (config, environment, data, dependency version) and one "it isn't where we're looking". For each, write what evidence would confirm it and what would refute it.

## 5. Investigate in parallel

In one message, spawn one `bosun:investigator` per top hypothesis (up to the parallel cap). Each prompt contains: the frame, the repro, its hypothesis, the competing hypotheses (so it hunts for evidence that tells them apart), and what would confirm or refute it.

Give an investigator `isolation: "worktree"` when it may need to instrument code, run `git bisect`, or run experiments that would disturb the main checkout. Otherwise run it without isolation and tell it to write only to a temp directory or `.bosun/scratch/`.

If agent teams are enabled and the user asked for a debate, spawn the investigators as teammates and have them challenge each other's conclusions.

## 6. Converge

- One hypothesis CONFIRMED with a complete causal chain: go to step 7.
- Several partly confirmed: they may combine (for example a race that only appears under one config). Check that together they explain every symptom.
- None confirmed: form the next round of hypotheses from what you learned (at most 3 rounds), then report it as inconclusive with the best leads and the next experiment.

## 7. Verify

Spawn `bosun:verifier` on the winning claim: it reproduces the problem independently and checks each link of the causal chain. UNCERTAIN or REFUTED sends you back to step 6.

## 8. Report

Write `.bosun/investigations/<YYYY-MM-DD>-<slug>.md`: summary; root cause with `path:line` and evidence; the causal chain; why it wasn't caught; fix options with trade-offs and a recommendation; the regression test; related risks elsewhere. Show the user a short version: the root cause in two sentences, your confidence, and the recommended fix.

Clean up: once you've confirmed investigator worktrees hold only experiments, remove them (`git worktree remove --force <path>`) and delete their branches.

## 9. Fix (with --fix, or when the user agrees)

Small fix: spawn `bosun:implementer` (worktree) with a test-first brief: the regression test must fail before the fix and pass after it. Gate it with `bosun:code-reviewer`, then merge it into the current branch as in the build pipeline. Large fix: hand over to `/bosun:plan` with the report as input.
