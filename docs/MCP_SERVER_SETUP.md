# MCP Server Setup

Release: `v0.3.4-beta`.

agent-sudo includes a standard stdio MCP server entrypoint:

```bash
agent-sudo-mcp
```

The server implements standard MCP stdio transport using newline-delimited JSON-RPC messages (one JSON object per line, ended by a single newline character `\n`, with no headers). This allows it to work out-of-the-box with standard MCP clients such as Claude Desktop and Cursor.

The server exposes three tools:

- `read_file`
- `write_file`
- `run_shell_command`

Every tool call is routed through:

```text
MCP client
-> agent-sudo-mcp
-> agent_sudo.mcp_gateway.MCPGateway
-> PermissionGateway.evaluate()
-> local demo executor
```

## Generic MCP Config

Use this shape for MCP clients that accept a command-based stdio server:

```json
{
  "mcpServers": {
    "agent-sudo": {
      "command": "agent-sudo-mcp",
      "args": [
        "--audit-log",
        ".agent-sudo/mcp-audit.jsonl",
        "--pending-approvals-file",
        ".agent-sudo/pending_approvals.json"
      ]
    }
  }
}
```

## Claude Desktop Example

Add an entry like this to the local Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "agent-sudo": {
      "command": "agent-sudo-mcp",
      "args": [
        "--audit-log",
        ".agent-sudo/mcp-audit.jsonl",
        "--pending-approvals-file",
        ".agent-sudo/pending_approvals.json"
      ]
    }
  }
}
```

Use only fake examples in committed docs and tests. Keep local policy files, audit logs, and approval config out of source control.

## Tool Behavior

- `read_file` is allowed by the default policy (unless targeting a protected configuration or sensitive file, which is BLOCKED).
- `write_file` requires approval or a matching delegation.
- `run_shell_command` is critical by default.
- destructive shell commands are blocked before execution.

## Pending Approvals

MCP clients are normally non-interactive. If an MCP request requires approval and there is no TTY, agent-sudo creates a pending approval instead of executing the tool.

The MCP response includes:

```json
{
  "executed": false,
  "approval_request_id": "00000000-0000-4000-8000-000000000000",
  "approval_command": "agent-sudo approve 00000000-0000-4000-8000-000000000000"
}
```

Approve or deny from a local terminal:

```bash
agent-sudo approvals list
agent-sudo approve APPROVAL_ID
agent-sudo deny APPROVAL_ID
```

Critical approvals require the local passphrase configured by `agent-sudo init-approval`. After approval, retry the same MCP tool call; the approval is consumed once and marked `USED`.

See [Pending Approvals](PENDING_APPROVALS.md) for the full workflow.

## MCP Delegation Example

Create a scoped delegation that lets an MCP client write only inside the demo directory:

```bash
mkdir -p /tmp/agent-sudo-demo
agent-sudo delegate create \
  --actor mcp-client \
  --allow-action write_file \
  --allow-path '/tmp/agent-sudo-demo/**' \
  --ttl-seconds 900 \
  --max-uses 3 \
  --reason "temporary MCP demo write access" \
  --delegations-file /tmp/agent-sudo-demo/delegations.json
```

Start the MCP server with the delegation store and an audit log:

```bash
agent-sudo-mcp \
  --delegations-file /tmp/agent-sudo-demo/delegations.json \
  --audit-log /tmp/agent-sudo-demo/audit.jsonl
```

Then call `write_file` from an MCP client with:

```json
{
  "name": "write_file",
  "arguments": {
    "path": "/tmp/agent-sudo-demo/test.txt",
    "content": "hello from mcp\n"
  }
}
```

Verify the audit log:

```bash
agent-sudo verify-audit /tmp/agent-sudo-demo/audit.jsonl
```

## Verification

Run:

```bash
python3 scripts/check_no_personal_data.py
python3 -m unittest discover -s tests
```

The MCP subprocess integration test starts `agent-sudo-mcp`, sends `initialize`, lists tools, calls `read_file`, calls a blocked shell command, and verifies the audit log.

## Bypass Risk

agent-sudo only enforces calls routed through this MCP server. If an agent keeps direct access to shell, file, browser, email, or desktop tools, those tools can bypass agent-sudo.
