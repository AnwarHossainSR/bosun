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
| `plugins/bosun/skills/<name>/SKILL.md` | User-facing workflows (`/bosun:<name>`) |
| `plugins/bosun/agents/<name>.md` | Subagent definitions (`bosun:<name>`) |
| `plugins/bosun/scripts/taskboard.py` | Task board CLI used by the skills (standard library only) |
| `plugins/bosun/hooks/` | Guard, activity log and context injection for bosun agents |
| `tests/` | Unit tests for the task board and the hooks |
| `examples/` | Example plans |

## Guidelines

**Prompts (skills and agents)**
- Keep instructions specific and checkable. Every agent ends with a `# BOSUN-RESULT` block; if you change its keys, update the parser in `hooks/bosun_hooks.py` and the tests.
- Keep the honesty rules: agents report only checks they ran, cite `path:line`, and mark unverified claims.
- Don't add instructions that depend on a tool or setting unless you've checked it exists in current Claude Code. Link the docs in your PR.
- Keep `SKILL.md` files under about 500 lines; move rarely needed detail into a `reference/` file.

**Python scripts**
- Standard library only, Python 3.10+.
- The hooks must fail open: an internal error exits 0 so a bug never blocks a user's session.
- Every guard rule needs tests for a command it blocks and a similar command it must allow.

**Commits and pull requests**
- Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `ci:`...).
- Keep pull requests focused. CI (tests and plugin validation) must pass before merging; pull requests are squash-merged.
- Update `CHANGELOG.md` and the README for user-visible changes.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE) that covers this project.
