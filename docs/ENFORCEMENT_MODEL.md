# Enforcement Model

`agent-sudo` is only enforceable when tool execution is routed through it.

If your agent keeps direct access to shell, browser, email, messaging, file-write, or credential tools, `agent-sudo` is advisory, not enforced.

## SDK Mode

SDK mode is for developers embedding `agent-sudo` in Python code.

The application imports `PermissionGateway`, converts native tool calls to `ActionRequest`, and wraps concrete tool execution with `SafeToolExecutor`.

Use this mode when you control the agent runtime code.

## CLI Wrapper Mode

CLI wrapper mode is for local agents that can call command-line tools.

The agent emits a tool-call JSON file and invokes:

```bash
agent-sudo generic-run tool_call.json --dry-run
```

For real execution, the wrapper should call `agent-sudo` first and only continue when the gateway returns `ALLOW`.

Use this mode when the agent can be configured to call a local command before dangerous tools execute.

## MCP/Proxy Mode

MCP/proxy mode is for tool protocols or desktop agents where a proxy can sit between the agent and the real tool.

The proxy receives a native tool call, converts it to the universal schema, asks `agent-sudo` for a decision, and then either blocks or forwards the call.

Use this mode when the agent supports tool servers, local proxies, or wrapper processes.

## Practical Warning

Remove or restrict direct dangerous tools where possible.
If direct access remains, an agent can bypass `agent-sudo`, intentionally or accidentally.

## Provenance

Every request should include provenance:

- origin type
- channel
- authentication state
- authentication method
- session ID
- request ID
- parent request ID
- delegation chain

Policy uses provenance to distinguish direct user intent from agent-internal steps and untrusted outside text.

`USER_DIRECT` with authentication can proceed to approval.
`EXTERNAL_CONTENT` cannot approve or escalate itself.
`UNKNOWN` provenance is treated conservatively and requires approval for tool use.
External content asking for tool use is blocked unless the user explicitly delegates a matching scope.
