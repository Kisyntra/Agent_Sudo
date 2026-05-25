# agent-sudo v0.2.0-beta MCP Server Release Report

## Summary

v0.2.0-beta adds the first real MCP enforcement path for agent-sudo. The project now includes a stdio MCP server entrypoint, `agent-sudo-mcp`, that exposes a small local tool surface and routes every tool call through the existing permission gateway before execution.

The implementation is suitable for beta validation, not a final stable release. The core path works, tests pass, and installability is confirmed. Package metadata now uses the Python packaging version `0.2.0b0`, while docs and CLI output use the human-facing label `v0.2.0-beta`.

## What Changed Since v0.1.0

- Added `agent-sudo-mcp` executable entrypoint.
- Added `agent_sudo.mcp_server`.
- Added stdio MCP JSON-RPC framing with `initialize`, `tools/list`, and `tools/call`.
- Exposed MCP tools:
  - `read_file`
  - `write_file`
  - `run_shell_command`
- Added `agent_sudo.mcp_gateway` dispatch layer.
- Added MCP validation helpers and subprocess integration tests.
- Changed default policy so `run_shell_command` is `CRITICAL`.
- Added path enforcement for high-risk local paths and `/tmp` demo writes.
- Added passphrase approval lockout after repeated failures.
- Added MCP setup and validation docs.

## Real MCP Flow

```text
MCP client
-> agent-sudo-mcp
-> agent_sudo.mcp_server.AgentSudoMCPServer
-> agent_sudo.mcp_gateway.MCPGateway
-> PermissionGateway.evaluate()
-> local demo executor
-> audit JSONL
```

The subprocess integration test starts `agent-sudo-mcp`, sends framed MCP messages, and verifies:

- `initialize` returns server metadata and tool capability.
- `tools/list` returns the three exposed tools.
- `tools/call read_file` is classified `SAFE`, allowed, executed, and audited.
- `tools/call run_shell_command` with a destructive command is classified `BLOCKED`, denied, not executed, and audited.

## Audit Results

### 1. MCP Protocol Correctness

Status: Beta-ready with limitations.

The server implements the minimal stdio shape expected by MCP clients:

- `Content-Length` message framing.
- JSON-RPC response objects.
- `initialize`.
- `notifications/initialized` ignored without response.
- `tools/list`.
- `tools/call`.

Limitations:

- No full MCP SDK dependency or formal conformance test suite.
- No cancellation, progress notifications, resource APIs, prompts, or logging capabilities.
- Error responses are basic JSON-RPC errors.
- The server does not validate all client capability fields.

### 2. Tool Schema Quality

Status: Adequate for beta.

Tool schemas are simple and readable:

- `read_file` requires `path`.
- `write_file` requires `path` and `content`.
- `run_shell_command` requires `command`.

Limitations:

- Schemas do not include additional constraints such as path examples, max content size, or enum-like hints for the shell demo allowlist.
- Descriptions are intentionally short.

### 3. Non-Interactive Approval Behavior

Status: Correct and conservative.

MCP server processes are usually non-interactive. Sensitive and critical actions do not silently approve themselves. If approval is required and no delegation applies, execution does not proceed.

This is correct for security but affects usability:

- `write_file` will not execute in normal MCP use unless approved by a usable approval provider or delegated.
- `run_shell_command` is `CRITICAL` by default and requires strong approval or a critical delegation.

### 4. Delegation Flow for MCP Clients

Status: Present but needs more documentation and examples.

`agent-sudo-mcp` accepts `--delegations-file`, and `build_server()` wires a `DelegationStore` into `PermissionGateway`. Delegated actions can be allowed before approval prompting.

Limitations:

- No dedicated MCP setup example currently shows creating a delegation for `mcp-client`.
- Delegation is matched by actor, action, and target path/command.
- Critical shell delegation requires `critical=true`.

### 5. Audit Logging

Status: Good.

The MCP server creates audit entries through `AuditLogger`. The integration test verifies audit entries for both allowed and denied calls.

Audit entries include the existing hash-chain fields:

- `previous_hash`
- `entry_hash`

Limitations:

- The MCP response transcript does not include the audit entry itself; it includes the gateway result. The audit file remains the source of truth.
- Default audit path is relative: `.agent-sudo/mcp-audit.jsonl`.

### 6. Security Regressions

Status: No obvious regression found in this audit.

Positive findings:

- `run_shell_command` is critical by default.
- Destructive shell commands are blocked before execution.
- Protected paths and credential-like paths are blocked for write/edit/delete.
- Non-interactive approval does not auto-approve.
- No network, cloud, telemetry, database, or credential handling was added.
- Personal-data scanner passes.

Residual risks:

- The MCP server executes `read_file` for any path that policy classifies as `SAFE`. This matches current policy, but it may be too broad for real deployments.
- The demo shell executor still exists as a local execution path for allowed commands after approval/delegation.
- Agents with direct shell/file tools can bypass agent-sudo entirely.

### 7. Documentation Accuracy

Status: Mostly accurate, with minor stale wording.

Accurate docs:

- `docs/MCP_SERVER_SETUP.md` explains the stdio server and bypass risk.
- `docs/MCP_GATEWAY.md` explains the dispatch layer and demo scope.
- `docs/REAL_WORLD_VALIDATION.md` explains the validation approach and limitations.

Stale or potentially confusing:

- `docs/MCP_GATEWAY.md` says the gateway does not implement a full MCP transport. That is still true for `MCPGateway`, but the repo now also has `agent_sudo.mcp_server`, which does implement a minimal stdio MCP server. The distinction is accurate but easy to misread.

### 8. Installability

Status: Installs and exposes the new executable.

Checked in a disposable venv:

```text
python3 -m pip install -e .
Successfully installed agent-sudo-0.2.0b0
```

Verified:

```text
agent-sudo-mcp --help
usage: agent-sudo-mcp [-h] [--policy POLICY] [--audit-log AUDIT_LOG]
                      [--delegations-file DELEGATIONS_FILE]
```

Verified:

```text
agent-sudo doctor
OK: Python version OK
OK: default policy exists
WARN: approval config exists - not initialized: run agent-sudo init-approval
OK: audit log writable
OK: delegation store writable
OK: no personal data in repo
```

Release blocker:

- None identified for a beta tag.

## Test Results

```text
python3 scripts/check_no_personal_data.py
Personal-data scan passed
```

```text
python3 -m unittest discover -s tests
Ran 88 tests
OK
```

```text
python3 -m pip install -e . in a venv
Successfully installed agent-sudo-0.2.0b0
```

```text
agent-sudo-mcp --help
OK
```

```text
agent-sudo doctor
OK with expected warning when approval config is not initialized
```

## Known Limitations

- Minimal MCP protocol support only.
- No formal MCP SDK conformance test.
- No interactive approval UX over MCP.
- Delegation is the practical path for non-interactive MCP clients.
- `read_file` is broad under the default policy.
- `write_file` is restricted by policy/gateway and demo path behavior.
- Direct agent access to dangerous tools remains a bypass.
- MCP support remains intentionally minimal.

## Security Assessment

The v0.2.0-beta MCP server is directionally safe for beta because denial and approval boundaries happen before execution. The design remains local-only and auditable. The highest security concern is not inside the MCP server; it is deployment bypass risk when an agent retains direct access to shell, file, browser, email, or desktop tools.

Recommendation: use the MCP server only with agents whose direct dangerous tools are removed or restricted.

## Tag Recommendation

Recommendation: tag `v0.2.0-beta`.

Do not tag stable `v0.2.0` yet. The MCP protocol support is intentionally minimal and should be exercised against more MCP clients before a stable release.

## Top 3 Next Improvements

1. Add formal MCP SDK compatibility tests or a fixture using a reference MCP client.
   Impact: high. Effort: medium.

2. Tighten default `read_file` policy with path scoping or explicit delegation for sensitive directories.
   Impact: high. Effort: medium.

3. Add an out-of-band approval flow designed for non-interactive MCP clients.
   Impact: high. Effort: medium.
