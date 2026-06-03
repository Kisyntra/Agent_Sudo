# MCP Server Setup

Applies to Agent_Sudo v0.5.x.

If you are evaluating Agent_Sudo for the first time, start with [Evaluate Agent_Sudo in 5 Minutes](../evaluate_5_minutes.md). This setup page is reference material after the first blocked -> delegated -> allowed once -> blocked again -> audit verified path succeeds.

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
      "command": "/path/to/agent-sudo-mcp",
      "args": [
        "--audit-log",
        "/path/to/mcp-audit.jsonl",
        "--pending-approvals-file",
        "/path/to/pending_approvals.json",
        "--workspace",
        "/path/to/project",
        "--notify"
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
      "command": "/path/to/agent-sudo-mcp",
      "args": [
        "--audit-log",
        "/path/to/mcp-audit.jsonl",
        "--pending-approvals-file",
        "/path/to/pending_approvals.json",
        "--workspace",
        "/path/to/project",
        "--notify"
      ]
    }
  }
}
```

Use only fake examples in committed docs and tests. Keep local policy files, audit logs, and approval config out of source control.

## Claude Code

Claude Code manages MCP servers with the `claude mcp` command — no manual JSON editing required. You only need `agent-sudo-mcp` on your `PATH` (`pipx install agent-sudo-mcp` provides it); a source checkout is **not** required.

First resolve the absolute path to the installed server, then register it:

```bash
which agent-sudo-mcp
# e.g. /Users/you/.local/bin/agent-sudo-mcp

claude mcp add agent-sudo -- /ABS/PATH/TO/agent-sudo-mcp \
  --audit-log "$HOME/.agent-sudo/mcp-audit.jsonl" \
  --pending-approvals-file "$HOME/.agent-sudo/pending_approvals.json" \
  --workspace /ABS/PATH/TO/your/project \
  --notify --open-approval-terminal
```

Everything after `--` is the server command and its arguments. Replace `/ABS/PATH/TO/your/project` with the absolute path to the project Claude Code should operate in.

Why these flags matter — do **not** drop `--audit-log` / `--pending-approvals-file`:

- **Absolute `--audit-log` and `--pending-approvals-file`.** The server's defaults are *relative* (`.agent-sudo/...`), resolved against the directory the MCP client launches the server from — which you do not control and is often not your project. With relative paths the audit log is written somewhere the verification step below cannot read, so it looks like nothing was protected even when it was. Pin absolute paths so the write location and your `agent-sudo audit list` read location match.
- **`--notify --open-approval-terminal`** (macOS only; no-ops elsewhere) give you an interactive approval prompt when a sensitive/critical action needs one. Without them an MCP client just receives `approval_required` and you must approve manually via `agent-sudo pending` / `agent-sudo approve`.

To generate this command with the executable path already resolved and the macOS flags included where applicable:

```bash
agent-sudo setup claude-code
```

Verify the server is registered, then confirm calls are actually routed through it — pass the **same** absolute audit-log path you configured above:

```bash
claude mcp list            # agent-sudo should be listed
claude mcp get agent-sudo  # shows the resolved command and args
agent-sudo audit list "$HOME/.agent-sudo/mcp-audit.jsonl"   # the call should appear
```

If a tool call does **not** appear, it bypassed Agent_Sudo (see [Bypass Risk](#bypass-risk)). A bare `agent-sudo audit list` with no path reads the *relative* default and will look empty unless you run it from the right directory — pass the absolute path.

Remove it with:

```bash
claude mcp remove agent-sudo
```

## Codex CLI

Codex CLI loads MCP servers from `~/.codex/config.toml`. Add an `[mcp_servers.agent-sudo]` block (create the file if it does not exist). As with Claude Code, you only need `agent-sudo-mcp` on your `PATH` — no source checkout.

```bash
which agent-sudo-mcp
# e.g. /Users/you/.local/bin/agent-sudo-mcp
```

```toml
# ~/.codex/config.toml
[mcp_servers.agent-sudo]
command = "/ABS/PATH/TO/agent-sudo-mcp"
args = [
  "--audit-log", "/ABS/HOME/.agent-sudo/mcp-audit.jsonl",
  "--pending-approvals-file", "/ABS/HOME/.agent-sudo/pending_approvals.json",
  "--workspace", "/ABS/PATH/TO/your/project",
  "--notify", "--open-approval-terminal",
]
```

Replace the paths with absolute values for your machine, then restart Codex CLI. The same reasoning as Claude Code applies: pin **absolute** `--audit-log` / `--pending-approvals-file` (the client launches the server from a directory you do not control, and relative defaults would hide the audit log), and `--notify --open-approval-terminal` enable the interactive macOS approval prompt (no-ops on other platforms). To generate this block with the executable path already resolved and the macOS flags included where applicable:

```bash
agent-sudo setup codex
```

Verify routing by running a tool inside a Codex session, then read the **same** absolute audit-log path you configured:

```bash
agent-sudo audit list "$HOME/.agent-sudo/mcp-audit.jsonl"   # the call should appear; if not, it bypassed agent-sudo
```

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
  "status": "approval_required",
  "executed": false,
  "approval_id": "00000000-0000-4000-8000-000000000000",
  "expires_in_seconds": 120,
  "action_summary": "run_shell_command by mcp-client on pwd",
  "risk": "CRITICAL",
  "approval_command": "agent-sudo approve 00000000-0000-4000-8000-000000000000"
}
```

Before you can approve pending requests, you must initialize your local approval passphrase:

```bash
agent-sudo init-approval
```

Then you can check, approve, or deny requests from a local terminal:

```bash
agent-sudo pending
agent-sudo approve APPROVAL_ID
agent-sudo approve 1
agent-sudo deny APPROVAL_ID
```

Critical approvals require the local passphrase configured by `agent-sudo init-approval`. After approval, retry the same MCP tool call; the approval is consumed once and marked `USED`.

Pending approvals default to 120 seconds. To adjust the window, set `AGENT_SUDO_APPROVAL_TTL_SECONDS` or start `agent-sudo-mcp` with `--approval-ttl-seconds`; values are clamped to 30-600 seconds.

See [Pending Approvals](../architecture/pending_approvals.md) for the full workflow.

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

## Running the MCP Server inside Docker

If you prefer to run the `Agent_Sudo` MCP server containerized:

1. **Build the Docker Image**:
   ```bash
   docker build -t agent-sudo-mcp .
   ```

2. **Run the Containerized MCP Server**:
   Mount your workspace folder so the container has access to it and specify the path via `--workspace`:
   ```bash
   docker run -i --rm -v /path/to/your/project:/app/workspace agent-sudo-mcp --workspace /app/workspace
   ```
