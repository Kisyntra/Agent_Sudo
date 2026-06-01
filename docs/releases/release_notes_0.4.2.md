# Release Notes: Agent_Sudo v0.4.2

This release adds registry metadata alignment and ownership verification markers to prepare Agent_Sudo for publication on the official MCP Registry.

## Highlights

- Adds the required hidden `mcp-name` verification marker to the root `README.md` file.
- Aligns `server.json` version metadata with the active codebase version (`0.4.2`).

## Why This Release

To register a PyPI-distributed server in the official MCP Registry, the registry verifies ownership by checking the package description on PyPI for a specific `mcp-name` marker. This release publishes the package containing this marker, clearing the path for registry listing.

## Validation

- `python3 -m unittest discover -s tests`
- `python3 -m ruff check .`
- `python3 scripts/validate_release.py --version 0.4.2`
- local wheel and source distribution build
- clean virtualenv install from the built wheel
- fresh-user README command verification from the built wheel
