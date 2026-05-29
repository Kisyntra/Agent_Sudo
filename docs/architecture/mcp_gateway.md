# MCP Gateway Demo

The MCP gateway is the first enforceable integration path in agent-sudo.

Flow:

```text
Agent or MCP client
-> agent-sudo MCP gateway
-> PermissionGateway.evaluate()
-> approved demo tool execution
```

This is different from `*-check` commands. Check commands are advisory. The MCP gateway owns dispatch for the demo tools, so a denied request is not executed by this process.

## Demo Scope

The prototype intentionally implements only local demo tools:

- `read_file`
- `write_file` inside `/tmp/agent-sudo-demo`
- `run_shell_command` for `pwd`, `ls`, `cat`, and `python3 -m unittest`

Shell execution is `CRITICAL` by default. To run a shell command without a passphrase prompt, create an explicit scoped delegation for the actor, command target, and action.

## Example

```python
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_gateway import dispatch_mcp_tool_call
from agent_sudo.policy import load_default_policy

gateway = PermissionGateway(load_default_policy())
result = dispatch_mcp_tool_call(
    {
        "actor": "mcp-client",
        "source": "user",
        "tool": "filesystem",
        "action": "read_file",
        "target": "README.md",
        "payload_summary": "Read project docs",
    },
    gateway,
    dry_run=True,
)
print(result.gateway_result.decision)
```

## Bypass Risk

If an agent keeps direct access to shell, browser, file, email, or messaging tools, agent-sudo is advisory for those tools. Real enforcement requires removing or restricting direct dangerous tools and routing execution through this gateway or another wrapper that calls `PermissionGateway.evaluate()` before execution.

## Current Limitations

- Local demo only.
- No server, database, cloud auth, telemetry, or UI.
- The gateway does not implement a full MCP transport yet; it accepts normalized JSON tool-call dictionaries.
- The demo shell allowlist is intentionally narrow and should not be treated as a general-purpose command runner.
