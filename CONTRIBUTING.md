# Contributing to bosun

Thanks for helping. bosun is a Claude Code plugin made of Markdown prompts (skills and agents), two small Python scripts, and tests. Most contributions touch one of those three.

## Ground rules

- Be kind and constructive. This project follows the [Code of Conduct](CODE_OF_CONDUCT.md).
- Security problems go through private reporting, not public issues. See [SECURITY.md](SECURITY.md).
- Open an issue before large changes (a new workflow, a new agent, a change to the result format) so we can agree on the approach first.

## Development setup

You need git, Python 3.10+, and Claude Code (for `claude plugin validate` and trying changes).

```bash
git clone https://github.com/AnwarHossainSR/bosun.git
cd bosun
python3 -m unittest discover -s tests -v
claude plugin validate --strict . && claude plugin validate --strict ./plugins/bosun
```

Optional: `npm install -g @fission-ai/openspec@1.14.2` enables the test that runs OpenSpec's own validator on the example change (it's skipped when the CLI is missing). Set `OPENSPEC_TELEMETRY=0` to turn off OpenSpec's anonymous usage statistics.

Try your working copy without installing it:

```bash
claude --plugin-dir ./plugins/bosun
```

Or install it from your clone as a local marketplace (edits apply on the next session):

```bash
claude plugin marketplace add "$(pwd)"
claude plugin install bosun@bosun-marketplace
```

## Where things live

| Path | What it is |
|---|---|
| `.claude-plugin/marketplace.json` | The marketplace that lists the plugin |
| `plugins/bosun/.claude-plugin/plugin.json` | Plugin manifest (name, version) |
| `plugins/bosun/skills/<name>/SKILL.md` | User-facing workflows (`/bosun:<name>`). Text only some runs need lives in `reference/` beside it and is read on demand: the build's edge cases and crew route, the review's `--fix` |
| `plugins/bosun/agents/<name>.md` | Subagent definitions (`bosun:<name>`) |
| `plugins/bosun/scripts/taskboard.py` | Task board CLI used by the skills (standard library only) |
| `plugins/bosun/scripts/usage.py` | Token report from Claude Code's transcript files, for the end of every report (standard library only) |
| `plugins/bosun/hooks/` | Guard, activity log, result saving and context injection for bosun agents |
| `plugins/bosun/templates/` | Template for a project's `.bosun/config.json`, and the classic PLAN.md outline |
| `tests/` | Unit tests for the task board and the hooks |
| `examples/` | Example plans: `taskflow-40` (classic PLAN.md) and `openspec-todo-api` (OpenSpec change + board) |
| `docs/` | The guide and the README's diagram |

## Guidelines

**Prompts (skills and agents)**
- Keep instructions specific and checkable. Every word of a SKILL.md or agent file is paid for each time it loads, and a skill stays in the session's context: put text that only some runs need in a `reference/` file the skill reads when that path runs, and check the change with `claude plugin details bosun`. Every agent ends with a `# BOSUN-RESULT` block; if you change its keys, update the parser in `hooks/bosun_hooks.py` and the tests.
- Keep the honesty rules: agents report only checks they ran, cite `path:line`, and mark unverified claims.
- Don't add instructions that depend on a tool or setting unless you've checked it exists in current Claude Code. Link the docs in your PR.
- Keep `SKILL.md` files under about 500 lines; move rarely needed detail into a `reference/` file.
- Every prompt word is paid on every run, and frontmatter descriptions in every session. Keep descriptions to one or two short clauses, don't repeat what the startup hook already injects (project commands, output style, the result reminder), and hand agents file paths instead of pasted text. Compare `claude plugin details bosun` (always-on and per-invoke estimates) before and after a prompt change, and mention the difference in your PR.

**Python scripts**
- Standard library only, Python 3.10+.
- The hooks must fail open: an internal error exits 0 so a bug never blocks a user's session.
- Every guard rule needs tests for a command it blocks and a similar command it must allow.
- The OpenSpec readers in `taskboard.py` follow OpenSpec's own parsers. When you change one, add a fixture test and check the same fixture with the real `openspec validate` (and `openspec archive` for delta rules), so bosun never reports something OpenSpec accepts as an error, or the reverse, without saying why.

**Commits and pull requests**
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `ci:`...).
- Keep pull requests focused. CI (tests and plugin validation) must pass before merging; pull requests are squash-merged.
- Update `CHANGELOG.md` and the README for user-visible changes.

**Releasing**
- Raise `version` in `plugins/bosun/.claude-plugin/plugin.json` and `VERSION` in `plugins/bosun/scripts/taskboard.py` together (a test checks they match). Installed copies update only when `version` changes.
- Move the `[Unreleased]` entries in `CHANGELOG.md` under the new version and date.
- After the release pull request is merged, tag it from an up-to-date `main` with `claude plugin tag plugins/bosun --push`, which creates and pushes `bosun--v<version>`.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers this project.
