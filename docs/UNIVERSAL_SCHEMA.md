# Universal Tool-Call Schema

`agent-sudo` accepts a small JSON object that any local agent can emit before tool execution.

Required fields:

```json
{
  "actor": "agent-a",
  "agent_type": "generic",
  "source": "user",
  "source_trust": "USER_DIRECT",
  "tool": "filesystem",
  "action": "edit_file",
  "target": "/home/user/example/project/README.md",
  "payload_summary": "Edit project documentation",
  "payload_hash": "sha256:example-placeholder",
  "requested_at": "2026-01-01T00:00:00Z",
  "session_id": "session-example-001",
  "provenance": {
    "origin_type": "USER_DIRECT",
    "channel": "cli",
    "authenticated": true,
    "authentication_method": "local_session",
    "session_id": "session-example-001",
    "request_id": "request-example-001",
    "parent_request_id": "",
    "delegation_chain": []
  }
}
```

Fields:

- `actor`: the agent identity requesting the action, such as `codex`, `hermes`, `claude-desktop`, `openclaw`, `agent-a`, or `mcp-client`
- `agent_type`: runtime family, such as `codex`, `hermes`, `claude_desktop`, `openclaw`, `mcp`, `browser`, `terminal`, or `generic`
- `source`: where the instruction came from, such as `user`, `webpage`, `document`, or `agent_internal`
- `source_trust`: one of `USER_DIRECT`, `AGENT_INTERNAL`, `EXTERNAL_CONTENT`, or `UNKNOWN`
- `tool`: requested tool family, such as `filesystem`, `shell`, `browser`, `email`, or `messaging`
- `action`: requested action, such as `read_file`, `edit_file`, `run_shell_command`, `browser_click`, or `send_message`
- `target`: path, URL, element reference, recipient placeholder, or other target
- `payload_summary`: short human-readable description
- `payload_hash`: optional hash of the full payload stored outside the request
- `requested_at`: ISO-8601 timestamp
- `session_id`: opaque session identifier
- `provenance`: structured request origin metadata

## Provenance

`provenance.origin_type` values:

- `USER_DIRECT`
- `LOCAL_UI`
- `AGENT_INTERNAL`
- `EXTERNAL_CONTENT`
- `EXTERNAL_API`
- `UNKNOWN`

`provenance.channel` values:

- `cli`
- `desktop_app`
- `browser`
- `email`
- `webpage`
- `api`
- `mcp`
- `unknown`

`provenance.authentication_method` values:

- `none`
- `local_session`
- `passphrase`
- `token`
- `signature`
- `unknown`

Lineage fields:

- `session_id`: session that produced the request
- `request_id`: current request identifier
- `parent_request_id`: upstream request that caused this action
- `delegation_chain`: delegation token IDs involved in the request path

Unknown tools are not trusted.
They normalize to `unknown_tool_call`, classify as `SENSITIVE`, and require approval.

External content is data, not instructions.
Requests with `EXTERNAL_CONTENT` or `UNKNOWN` trust never get silent auto-execution.
External content cannot approve or escalate itself.
