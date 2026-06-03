# First Run Reference

For first-time evaluation, start with [Evaluate Agent_Sudo in 5 Minutes](evaluate_5_minutes.md). This page is the expanded reference version of the same validated MCP workflow:

```text
blocked
↓
delegated
↓
allowed once
↓
blocked again
↓
audit verified
```

Expected time:

- first successful evaluation after install: under 5 minutes
- source-checkout setup if Python packaging is not ready: 2 to 5 extra minutes

## 1. Install

From the repository root:

```bash
python3 -m pip install -e .
```

If your Python install blocks global editable installs, use a virtual environment outside the repo so local venv paths do not interfere with repository hygiene checks:

```bash
python3 -m venv /tmp/agent-sudo-venv
. /tmp/agent-sudo-venv/bin/activate
python3 -m pip install -e .
```

Verify the CLI:

```bash
agent-sudo --version
agent-sudo doctor
```

If `agent-sudo-mcp` is not on `PATH`, run the MCP server as:

```bash
python3 -m agent_sudo.mcp_server --help
```

> Passphrase setup (`agent-sudo init-approval`) is **not** required for this
> first-run path. The deny → delegate → allow-once → deny loop below uses a
> scoped delegation, not interactive approval. Passphrase setup is covered in
> step 9, after you have seen the engine work.

## 2. Prepare Local Demo State

Use `/tmp` for first-run state so no local audit or delegation files are created in the checkout:

```bash
rm -rf /tmp/agent-sudo-first-run
mkdir -p /tmp/agent-sudo-first-run

export AGENT_SUDO_AUDIT=/tmp/agent-sudo-first-run/audit.jsonl
export AGENT_SUDO_DELEGATIONS=/tmp/agent-sudo-first-run/delegations.json
```

## 3. Start MCP Server

In a real MCP client, configure the server command:

```bash
agent-sudo-mcp \
  --audit-log "$AGENT_SUDO_AUDIT" \
  --delegations-file "$AGENT_SUDO_DELEGATIONS"
```

For a self-contained demo, the command below starts the `agent-sudo-mcp` server as a subprocess and sends one MCP `run_shell_command` request for `pwd`.

## 4. Run Demo: Initial Deny

```bash
python3 - <<'PY'
import json
import os
import subprocess

audit = os.environ["AGENT_SUDO_AUDIT"]
delegations = os.environ["AGENT_SUDO_DELEGATIONS"]

process = subprocess.Popen(
    [
        "agent-sudo-mcp",
        "--audit-log",
        audit,
        "--delegations-file",
        delegations,
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

def request(message):
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    process.stdin.write(body + b"\n")
    process.stdin.flush()
    line = process.stdout.readline()
    return json.loads(line.decode("utf-8"))

request({
    "jsonrpc": "2.0",
    "id": "init",
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "first-run", "version": "0"},
    },
})

response = request({
    "jsonrpc": "2.0",
    "id": "pwd-1",
    "method": "tools/call",
    "actor": "codex",
    "params": {
        "name": "run_shell_command",
        "arguments": {"command": "pwd"},
    },
})

content = response["result"]["structuredContent"]
print("pwd-1", content["approval_decision"], content["execution_result"]["executed"])

process.stdin.close()
process.wait(timeout=2)
PY
```

Expected output:

```text
pwd-1 REQUIRE_STRONG_APPROVAL False
```

That is the expected first result. Shell is `CRITICAL`, so MCP does not execute it without approval or delegation.

## 5. Verify Audit Log

```bash
agent-sudo verify-audit "$AGENT_SUDO_AUDIT"
```

Expected output:

```text
audit log verified
```

If `agent-sudo` is not on `PATH`, use:

```bash
python3 -m agent_sudo.gateway verify-audit "$AGENT_SUDO_AUDIT"
```

## 6. Create One-Use Delegation

Grant only actor `codex` one use of `run_shell_command` for target `pwd`:

```bash
agent-sudo delegate create \
  --actor codex \
  --allow-action run_shell_command \
  --allow-path pwd \
  --ttl-seconds 300 \
  --max-uses 1 \
  --critical \
  --reason "first-run pwd demo" \
  --delegations-file "$AGENT_SUDO_DELEGATIONS"
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m agent_sudo.gateway delegate create \
  --actor codex \
  --allow-action run_shell_command \
  --allow-path pwd \
  --ttl-seconds 300 \
  --max-uses 1 \
  --critical \
  --reason "first-run pwd demo" \
  --delegations-file "$AGENT_SUDO_DELEGATIONS"
```

## 7. Run Demo: Allow Once, Then Deny

```bash
python3 - <<'PY'
import json
import os
import subprocess

audit = os.environ["AGENT_SUDO_AUDIT"]
delegations = os.environ["AGENT_SUDO_DELEGATIONS"]

process = subprocess.Popen(
    [
        "agent-sudo-mcp",
        "--audit-log",
        audit,
        "--delegations-file",
        delegations,
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

def request(message):
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    process.stdin.write(body + b"\n")
    process.stdin.flush()
    line = process.stdout.readline()
    return json.loads(line.decode("utf-8"))

request({
    "jsonrpc": "2.0",
    "id": "init",
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "first-run", "version": "0"},
    },
})

for request_id in ["pwd-2", "pwd-3"]:
    response = request({
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "actor": "codex",
        "params": {
            "name": "run_shell_command",
            "arguments": {"command": "pwd"},
        },
    })
    content = response["result"]["structuredContent"]
    execution = content["execution_result"]
    print(
        request_id,
        content["approval_decision"],
        content["approval_method"],
        execution["executed"],
        execution["reason"],
    )

process.stdin.close()
process.wait(timeout=2)
PY
```

Expected output:

```text
pwd-2 ALLOW DELEGATION True executed
pwd-3 DENY DELEGATION False delegation token <token_id> mismatched: token exhausted
```

## 8. Verify Final Audit Log

List the decisions you just produced:

```bash
agent-sudo audit list --limit 5 "$AGENT_SUDO_AUDIT"
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m agent_sudo.gateway audit list --limit 5 "$AGENT_SUDO_AUDIT"
```

Look for the `run_shell_command` / `pwd` decisions: `REQUIRE_STRONG_APPROVAL`, `ALLOW`, then `DENY`. The table may include auxiliary MCP approval rows.

Verify the hash chain:

```bash
agent-sudo verify-audit "$AGENT_SUDO_AUDIT"
```

Expected output:

```text
audit log verified
```

Run the read-only routing report:

```bash
agent-sudo verify-routing
```

Fallback when the console script is not on `PATH`:

```bash
python3 -m agent_sudo.gateway verify-routing
```

You have now validated:

- MCP routing
- critical shell enforcement
- scoped one-use delegation
- delegation exhaustion
- readable audit decisions
- audit-chain verification
- observed routing signals

## 9. Initialize Approval (optional — for interactive approvals)

The first-value loop above needed no passphrase. You only need this step when
you want **interactive human approval** of sensitive actions (instead of, or in
addition to, scoped delegations) — for example when wiring Agent_Sudo into a
real MCP client.

Create the local approval passphrase hash:

```bash
agent-sudo init-approval
```

Use a unique local passphrase. Do not reuse an account password. This writes
local approval state under `~/.agent-sudo/`. Do not commit that directory.

## GIF Or Video Capture Workflow

Use the shortest terminal story:

1. Show the first MCP request returning `REQUIRE_STRONG_APPROVAL`.
2. Show the one-use `agent-sudo delegate create` command.
3. Show the second MCP request returning `ALLOW DELEGATION True executed`.
4. Show the third request returning `DENY DELEGATION False delegation token is exhausted`.
5. End on `agent-sudo verify-audit "$AGENT_SUDO_AUDIT"` returning `audit log verified`.

Recommended capture tools:

- macOS built-in screen recording: `Cmd+Shift+5`, record a terminal window, then trim in QuickTime.
- `asciinema`: record a terminal session and convert to GIF with `agg`.
- `vhs`: script the terminal demo into a repeatable GIF.

Keep the capture under 45 seconds. The strongest story is deny -> one-use delegation -> allow once -> deny exhausted.

## Note on File Read Access

Under the default policy, most files are readable by default (`SAFE` and auto-allowed). However, files containing sensitive configuration data (such as those under `~/.ssh/` or `~/.config/`, `.env` files, or files with keywords like `auth` or `secret` in their path) are classified as `BLOCKED` and denied by default.

## Resetting a Forgotten Passphrase

If you forget your local passphrase, you can reset it by running the initialization command again:

```bash
agent-sudo init-approval
```

Resetting the passphrase has the following secure behavior:
* **No passphrase recovery**: The old passphrase cannot be recovered because it is stored only as a one-way PBKDF2 hash.
* **Revokes delegations**: All existing delegation tokens are immediately revoked to prevent compromised credentials from surviving the reset.
* **Cancels pending approvals**: All active `PENDING` and `APPROVED` approvals are transitioned to `DENIED` with the reason `"passphrase was reset"`.
* **Preserves audit logs**: Existing audit logs are preserved (none are deleted).
* **Logs reset event**: A `passphrase_reset` event is cryptographically appended to the audit log, recording the counts of revoked delegations and canceled approvals.

To run this command non-interactively (e.g., in automated scripts or tests), pass the `--force` flag:

```bash
agent-sudo init-approval --force
```
