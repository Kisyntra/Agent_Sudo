# First Run

This guide takes a new user from a fresh checkout to the validated MCP workflow:

```text
agent requests shell
-> denied

user grants one-use delegation
-> allowed once

same request again
-> denied because delegation is exhausted
```

Expected time:

- first successful install: 2 to 5 minutes
- first successful MCP demo: 5 to 10 minutes

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

## 2. Initialize Approval

Create the local approval passphrase hash:

```bash
agent-sudo init-approval
```

Use a unique local passphrase. Do not reuse an account password.

This writes local approval state under `~/.agent-sudo/`. Do not commit that directory.

## 3. Prepare Local Demo State

Use `/tmp` for first-run state so no local audit or delegation files are created in the checkout:

```bash
rm -rf /tmp/agent-sudo-first-run
mkdir -p /tmp/agent-sudo-first-run

export AGENT_SUDO_AUDIT=/tmp/agent-sudo-first-run/audit.jsonl
export AGENT_SUDO_DELEGATIONS=/tmp/agent-sudo-first-run/delegations.json
```

## 4. Start MCP Server

In a real MCP client, configure the server command:

```bash
agent-sudo-mcp \
  --audit-log "$AGENT_SUDO_AUDIT" \
  --delegations-file "$AGENT_SUDO_DELEGATIONS"
```

For a checkout-first demo, the command below starts `agent_sudo.mcp_server` as a subprocess and sends one MCP `run_shell_command` request for `pwd`.

## 5. Run Demo: Initial Deny

```bash
python3 - <<'PY'
import json
import os
import subprocess

audit = os.environ["AGENT_SUDO_AUDIT"]
delegations = os.environ["AGENT_SUDO_DELEGATIONS"]

process = subprocess.Popen(
    [
        "python3",
        "-m",
        "agent_sudo.mcp_server",
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

## 6. Verify Audit Log

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

## 7. Create One-Use Delegation

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

## 8. Run Demo: Allow Once, Then Deny

```bash
python3 - <<'PY'
import json
import os
import subprocess

audit = os.environ["AGENT_SUDO_AUDIT"]
delegations = os.environ["AGENT_SUDO_DELEGATIONS"]

process = subprocess.Popen(
    [
        "python3",
        "-m",
        "agent_sudo.mcp_server",
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

## 9. Verify Final Audit Log

```bash
agent-sudo verify-audit "$AGENT_SUDO_AUDIT"
```

Expected output:

```text
audit log verified
```

You have now validated:

- MCP routing
- critical shell enforcement
- scoped one-use delegation
- delegation exhaustion
- audit-chain verification

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
