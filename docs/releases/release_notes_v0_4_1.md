# Release Notes: Agent_Sudo v0.4.1

Patch release for first-user MCP onboarding.

## Highlights

- Adds `agent-sudo audit list`, a human-readable audit log viewer with `--limit`, `--json`, and optional audit-log path support.
- Adds `agent-sudo workspace set <path>` and `agent-sudo workspace show` so Claude Desktop users can persist a fixed workspace once in `~/.agent-sudo/config.json`.
- Fixes `agent-sudo doctor` for installed package users by skipping the contributor-only personal-data scan when the source-tree scanner is not available.
- Updates README and Claude Desktop setup docs to clarify the protected MCP setup flow, audit verification, and native-tool bypass boundaries.

## Why This Release

The `main` README now documents commands that were not present in the PyPI `v0.4.0` package, especially `agent-sudo workspace set`. A fresh user installing from PyPI could follow the README and hit a hard blocker. `v0.4.1` aligns the package with the documented onboarding path.

## Validation

- `python3 -m unittest discover -s tests`
- `python3 -m ruff check .`
- `python3 scripts/validate_release.py --version 0.4.1`
- local wheel and source distribution build
- clean virtualenv install from the built wheel
- fresh-user README command verification from the built wheel
