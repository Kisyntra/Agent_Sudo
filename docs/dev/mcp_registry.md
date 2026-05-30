# MCP Registry Publication Preparation

This document outlines the preparation steps, requirements, and timing analysis for publishing the `Agent_Sudo` MCP server to the official Model Context Protocol Registry.

---

## 1. Publication Deferral Status

Official MCP Registry publication is deferred until the next normal patch release because PyPI v0.4.0 is immutable and does not contain the required mcp-name verification marker.

### Next release must include:
* README marker: `<!-- mcp-name: io.github.kisyntra/agent-sudo-mcp -->`
* `server.json`
* PyPI package release
* `mcp-publisher publish`

---

## 2. Verified Registry Requirements

The official registry (`registry.modelcontextprotocol.io`) requires the `mcp-publisher` CLI tool to submit server metadata.

### Hard Constraints
* **Namespace Binding**: Because we use GitHub OIDC device flow authentication under the `Kisyntra` account, our registry namespace is locked to `io.github.kisyntra/`. The server name in `server.json` **must** match `io.github.kisyntra/agent-sudo-mcp`.
* **Automated Package Check**: The registry pulls the package metadata directly from PyPI. It expects the published `README.md` to contain a verification string matching the server name.
* **No Verification Bypasses**: The registry validation script will reject any publication attempts if the ownership verification marker is missing in the package's published readme file on PyPI.

---

## 3. README Marker Staging Plan

To satisfy the automated PyPI check without cluttering the public-facing documentation, we will insert the verification marker as a hidden HTML comment at the top of the root `README.md`.

### Target Snippet
Add the following snippet right below the main title in [README.md](file:///Volumes/Storage/Agent_Sudo/README.md):
```markdown
<!-- mcp-name: io.github.kisyntra/agent-sudo-mcp -->
```
