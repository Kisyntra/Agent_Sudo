# MCP Server Setup

Release: `v0.2.0-beta`.

agent-sudo includes a stdio MCP server entrypoint:

```bash
agent-sudo-mcp
```

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
        ".agent-sudo/mcp-audit.jsonl"
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
        ".agent-sudo/mcp-audit.jsonl"
      ]
    }
  }
}
```

Use only fake examples in committed docs and tests. Keep local policy files, audit logs, and approval config out of source control.

## Tool Behavior

- `read_file` is allowed by the default policy.
- `write_file` requires approval or a matching delegation.
- `run_shell_command` is critical by default.
- destructive shell commands are blocked before execution.

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
