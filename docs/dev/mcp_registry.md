# MCP Registry Publication Status

This document records the requirements and current status for publishing the `Agent_Sudo` MCP server to the official Model Context Protocol Registry.

---

## 1. Current Publication Status

Official MCP Registry publication is active.

* Registry listing: [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/v0/servers?search=agent-sudo-mcp)
* Server name: `io.github.Kisyntra/agent-sudo-mcp`
* PyPI package: [`agent-sudo-mcp` v0.4.3](https://pypi.org/project/agent-sudo-mcp/)
* Repository metadata: `server.json`

---

## 2. Verified Registry Requirements

The official registry (`registry.modelcontextprotocol.io`) requires the `mcp-publisher` CLI tool to submit server metadata.

### Hard Constraints
* **Namespace Binding**: Because publication uses GitHub authentication under the `Kisyntra` account, the server name in `server.json` must match `io.github.Kisyntra/agent-sudo-mcp`.
* **Automated Package Check**: The registry pulls the package metadata directly from PyPI. It expects the published `README.md` to contain a verification string matching the server name.
* **No Verification Bypasses**: The registry validation script will reject any publication attempts if the ownership verification marker is missing in the package's published readme file on PyPI.

---

## 3. README Marker

To satisfy the automated PyPI check without cluttering the public-facing documentation, the root `README.md` includes a hidden HTML verification marker.

### Current Snippet
```markdown
<!-- mcp-name: io.github.Kisyntra/agent-sudo-mcp -->
```
