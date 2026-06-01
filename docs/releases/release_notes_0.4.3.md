# Release Notes: Agent_Sudo v0.4.3

This release capitalizes the registry name in the ownership verification marker to align with the case-sensitive permissions of the Kisyntra GitHub organization namespace in the official MCP Registry.

## Highlights

- Updates the hidden `mcp-name` verification marker in `README.md` to use the capitalized namespace: `io.github.Kisyntra/agent-sudo-mcp`.
- Bumps registry version and PyPI package version reference to `0.4.3` in `server.json`.

## Why This Release

The official MCP Registry enforces case-sensitive validation on publisher namespaces. Since the `Kisyntra` organization namespace on GitHub is capitalized, the registry requires the server name to be `io.github.Kisyntra/agent-sudo-mcp` (capital `K`), which in turn requires the PyPI package README verification marker to match this casing exactly. This release publishes the corrected marker on PyPI.
