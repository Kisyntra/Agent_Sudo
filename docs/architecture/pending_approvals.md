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
  "status": "approval_required",
  "executed": false,
  "approval_id": "00000000-0000-4000-8000-000000000000",
  "expires_at": "2026-05-26T20:00:00Z",
  "expires_in_seconds": 120,
  "action_summary": "run_shell_command by mcp-client on pwd",
  "risk": "CRITICAL",
  "approval_command": "agent-sudo approve 00000000-0000-4000-8000-000000000000"
}
```

The original tool call is not executed.

Pending approvals default to 120 seconds. The TTL is clamped between 30 and 600 seconds and can be configured with either:

```bash
AGENT_SUDO_APPROVAL_TTL_SECONDS=240 agent-sudo-mcp
agent-sudo-mcp --approval-ttl-seconds 240
```

## Desktop Notifications

To avoid constantly polling or watching the terminal for pending requests, you can optionally enable native desktop alerts:
- **CLI/MCP Argument**: Start the server or gateway run with `--notify` (e.g. `agent-sudo-mcp --notify`).
- **Environment Variable**: Set `AGENT_SUDO_NOTIFY=1` in your environment.

When a pending approval is created, a macOS user notification is triggered (via `osascript`) warning the operator to run the approval command.

## Guided Terminal Helper (`agent-sudo approval-helper`)

For a more streamlined local UX, you can run the guided approval helper:

```bash
agent-sudo approval-helper
```

This interactive utility:
1. Verifies if your approval passphrase configuration exists. If missing, it prints setup onboarding guidance.
2. Formats and prints active pending approvals.
3. Guides you through approving or denying each pending request interactively using a `[y/N]` prompt. If approved, it calls the standard passphrase prompt (if critical) or CLI confirm (if sensitive).
4. Exits when the queue is processed, or can run continuously to poll for new requests by passing the `--watch` flag:
   ```bash
   agent-sudo approval-helper --watch
   ```

## Auto-Opening Terminal for Approvals

To fully automate the terminal opening loop on macOS:
- **CLI/MCP Argument**: Start the server or gateway run with `--open-approval-terminal` (e.g. `agent-sudo-mcp --open-approval-terminal`).
- **Environment Variable**: Set `AGENT_SUDO_OPEN_APPROVAL_TERMINAL=1` in your environment.

When a pending approval is created, `Agent_Sudo` automatically spawns a new Terminal.app window running `agent-sudo approval-helper --auto-opened`.

### Auto-Opened Terminal UX & Behavior

When launched automatically:
1. **Suppressed Shell Noise & Minimal Display**: The helper runs in a clean window. It clears the screen immediately and suppresses macOS login shell startup noise (e.g. motd, zsh warnings, powerlevel10k details, and full Python execution paths).
2. **Safe Target Summary**: Any absolute paths or full python executable paths are truncated to their basenames to prevent leaking sensitive local system structures.
3. **Auto-Closing Countdown**:
   - If there is exactly **one** pending approval when the terminal opens, and you successfully approve or deny it, the terminal will display `Approved. Closing in 3 seconds...` (or `Denied. Closing in 3 seconds...`), wait 3 seconds, and automatically close the window.
4. **Safe Keep-Open Modes**:
   - The terminal window **will not auto-close** if:
     - No approval config exists (setup onboarding is required).
     - No pending approvals are found.
     - Multiple pending approvals exist in the queue.
     - Verification fails (incorrect passphrase).
     - Watch mode is active (`--watch`).
     - An unexpected error or crash occurs.
   - In any of these keep-open scenarios, the terminal helper blocks on a `Press Enter to exit...` prompt so you can read the warnings, setup instructions, or error logs before closing.

> [!CAUTION]
> **Safety Design**:
> - It never auto-approves or auto-enters passphrases.
> - It never passes sensitive tool command arguments or private environment variables through the window command string (it only calls `approval-helper` safely using `sys.executable` and an optional custom path to the `pending_approvals.json` store with the `--auto-opened` flag).
> - Terminal opening errors are caught internally and logged to stderr without blocking or interrupting the approval generation.

## CLI Workflow

List pending approvals:

```bash
agent-sudo pending
agent-sudo approvals list
```

Approve one request:

```bash
agent-sudo approve APPROVAL_ID
agent-sudo approve 1
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

## Delegation Mismatch Troubleshooting

When evaluating delegation tokens, agent-sudo checks all active tokens. If a token exists but does not match the request, agent-sudo returns detailed diagnostics explaining which field(s) mismatched (e.g. actor mismatch, action mismatch, path mismatch, critical flag missing, token expired, revoked, or exhausted) along with expected vs. actual values.

> [!IMPORTANT]
> By default, standard MCP clients (like Claude Desktop or Cursor) connect as the actor `mcp-client`. When creating delegations for MCP tools, ensure the `--actor` argument matches `mcp-client` (or the specific actor name passed in the `ActionRequest`), otherwise requests will fail with an actor mismatch diagnostic.
