## What and why

<!-- What does this change, and why is it needed? Link the issue it resolves, if any (for example "Closes #123"). -->

## How it was tested

<!-- Commands you ran and what you saw. For agent or skill prompt changes, describe the real task you tried it on. -->

## Checklist

- [ ] `python3 -m unittest discover -s tests` passes
- [ ] `claude plugin validate --strict .` and `claude plugin validate --strict ./plugins/bosun` pass
- [ ] README and CHANGELOG updated for user-visible changes
- [ ] No secrets, personal data or machine-specific paths in the diff
- [ ] Guard rule changes include tests for both a blocked and an allowed command
