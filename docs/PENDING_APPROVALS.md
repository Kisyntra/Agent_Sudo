# Pending Approvals

Non-interactive MCP clients usually run without a terminal. When an MCP tool call needs approval, agent-sudo does not ask that process to type `yes` or a passphrase. Instead, it creates a local pending approval request and returns a command for the user to run in a separate terminal.

```text
MCP client
-> agent-sudo-mcp
-> PermissionGateway.evaluate()
-> pending approval created
-> user approves or denies locally
-> MCP client retries the same tool call
-> approved request is consumed once
```

Pending approvals are stored locally:

```text
~/.agent-sudo/pending_approvals.json
```

Do not commit this file. It can include local action targets and payload summaries.

## MCP Response

When a request requires approval and no TTY is available, the MCP result includes an approval request ID and a local approval command:

```json
{
  "executed": false,
  "approval_request_id": "00000000-0000-4000-8000-000000000000",
  "approval_command": "agent-sudo approve 00000000-0000-4000-8000-000000000000"
}
```

The original tool call is not executed.

## CLI Workflow

List pending approvals:

```bash
agent-sudo approvals list
```

Approve one request:

```bash
agent-sudo approve APPROVAL_ID
```

Deny one request:

```bash
agent-sudo deny APPROVAL_ID
```

Critical actions require the local approval passphrase configured by:

```bash
agent-sudo init-approval
```

Sensitive actions can be approved from the CLI without the critical passphrase. External content cannot approve itself.

## Retry Semantics

After approval, the client retries the exact same tool call. agent-sudo matches the retried action against the approved pending request.

- `APPROVED` requests are valid once.
- after successful use, the request becomes `USED`.
- a second retry is blocked.
- `DENIED` requests cannot be used.
- expired requests cannot be used.

Every state change is written to the audit log when an audit log is configured.

## Example

Start the MCP server with explicit local state files:

```bash
agent-sudo-mcp \
  --audit-log /tmp/agent-sudo-demo/audit.jsonl \
  --pending-approvals-file /tmp/agent-sudo-demo/pending_approvals.json
```

If a client requests `run_shell_command` with `pwd`, agent-sudo returns a pending approval because shell commands are critical by default.

Approve from a local terminal:

```bash
agent-sudo approve APPROVAL_ID \
  --pending-approvals-file /tmp/agent-sudo-demo/pending_approvals.json \
  --audit-log /tmp/agent-sudo-demo/audit.jsonl
```

Then retry the same MCP tool call. The approved request is consumed once and later retries are blocked.
