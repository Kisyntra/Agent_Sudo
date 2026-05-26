# agent-sudo

Current public release: `v0.3.4-beta`.

`agent-sudo` is a local permission gateway for AI agents before they execute tools.
It exists because agents can confuse user intent, injected content, and agent-internal actions.
It protects local tool execution with policy checks, approvals, scoped delegation, provenance, and audit logs.
It cannot protect tools an agent can still access directly.
`agent-sudo` is not a sandbox.
Quickstart: install, run `agent-sudo init-approval`, then follow [First Run](docs/FIRST_RUN.md) for the MCP deny -> allow once -> deny demo.

## 5 Minute Quickstart

From a fresh checkout:

```bash
python3 -m pip install -e .
agent-sudo --version
agent-sudo doctor
agent-sudo init-approval
```

Then run the guided MCP demo:

```bash
cat docs/FIRST_RUN.md
```

The first-run path shows the core workflow:

```text
agent requests shell
-> denied

user grants one-use delegation
-> allowed once

same request again
-> denied because delegation is exhausted
```

Expected timing:

- first install: 2 to 5 minutes
- first MCP demo: 5 to 10 minutes

If console scripts are not on `PATH`, use the module form:

```bash
python3 -m agent_sudo.gateway doctor
python3 -m agent_sudo.mcp_server --help
```

## Why agent-sudo exists

AI agents can call powerful local tools, but they cannot always distinguish a direct user request from prompt injection, external content, stale session state, or an over-broad tool permission.

agent-sudo adds a local checkpoint before execution:

- classify the action
- apply least-privilege policy
- require approval or scoped delegation
- execute only after `ALLOW`
- record an auditable decision

This MVP is intentionally small:

- local files only
- no network calls
- no database
- no cloud auth
- no real credentials
- no destructive action execution

## Threat Model

AI agents can receive instructions from several places: the human operator, system prompts, tool outputs, websites, emails, documents, logs, and other agents.
The gateway assumes external content is data, never authority.

Primary risks addressed:

- prompt injection
- insecure or over-permissioned tools
- excessive agency
- missing human approval
- poor audit trails
- attempts to exfiltrate secrets or bypass policy

`agent-sudo` does not prove intent or identity. It reduces blast radius by making the requested action explicit, classifying risk, applying least-privilege policy, and preserving an audit trail.

The security boundary is provenance + policy + mandatory routing through the gateway. Keyword or phrase detection is not the boundary; it is only a convenience catch for obvious malicious instructions before the policy path runs.

## Install

From this directory:

```bash
python3 -m pip install -e .
```

If your Python install blocks system-wide package changes, use a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

Or run without installing:

```bash
python3 -m agent_sudo.gateway check examples/demo_requests.json
python3 -m agent_sudo.gateway run examples/demo_requests.json --dry-run
```

## Quickstart For Normal Users

1. Install locally:

```bash
python3 -m pip install -e .
```

2. Initialize approval:

```bash
agent-sudo init-approval
```

3. Run the demo:

```bash
agent-sudo run examples/demo_requests.json --dry-run
```

4. Read the decision:

- `ALLOW`: the request is allowed
- `DENY`: the request is blocked
- `REQUIRE_APPROVAL`: a sensitive action needs CLI confirmation
- `REQUIRE_STRONG_APPROVAL`: a critical action needs passphrase confirmation

## Quickstart For Developers

Wrap tool execution instead of calling tools directly:

```python
from agent_sudo.adapters.generic import from_generic_tool_call
from agent_sudo.executors import SafeToolExecutor
from agent_sudo.gateway import PermissionGateway
from agent_sudo.policy import load_default_policy

gateway = PermissionGateway(load_default_policy())
safe_executor = SafeToolExecutor(gateway, concrete_tool_executor)
request = from_generic_tool_call(tool_call)
result = safe_executor.execute(request)
```

Create scoped delegation tokens:

```bash
agent-sudo delegate create \
  --actor agent-a \
  --allow-action read_file \
  --allow-path ~/example/project-files \
  --ttl-seconds 7200 \
  --max-uses 20 \
  --reason "temporary project read access"
```

Verify audit logs:

```bash
agent-sudo verify-audit .agent-sudo/audit.jsonl
```

## CLI Examples

Classify and decide without approvals or audit writes:

```bash
agent-sudo check examples/demo_requests.json
```

Run through the gateway in dry-run mode:

```bash
agent-sudo run examples/demo_requests.json --dry-run
```

Check native agent tool-call dictionaries:

```bash
agent-sudo hermes-check examples/hermes_tool_call.json
agent-sudo codex-check examples/codex_tool_call.json
agent-sudo generic-check examples/generic_tool_call.json
agent-sudo generic-run examples/generic_tool_call.json --dry-run
```

For the first enforceable dispatch prototype, see [docs/MCP_GATEWAY.md](docs/MCP_GATEWAY.md). It routes MCP-style JSON tool calls through `PermissionGateway.evaluate()` before running the small local demo tool set.

For the stdio MCP server, see [docs/MCP_SERVER_SETUP.md](docs/MCP_SERVER_SETUP.md). It exposes `read_file`, `write_file`, and `run_shell_command` as MCP tools through `agent-sudo-mcp`.

For non-interactive MCP clients, approval-required requests create local pending approvals instead of executing. Review them with `agent-sudo approvals list`, approve with `agent-sudo approve APPROVAL_ID`, then retry the same MCP tool call once. See [docs/PENDING_APPROVALS.md](docs/PENDING_APPROVALS.md).

## Real MCP Example

The validated end-to-end flow is documented in [docs/END_TO_END_DEMO.md](docs/END_TO_END_DEMO.md) and [DEMO_TRANSCRIPT.md](DEMO_TRANSCRIPT.md).

Lifecycle:

```text
MCP client -> run_shell_command "pwd"
classification: CRITICAL
decision: REQUIRE_STRONG_APPROVAL
executed: false
```

Then a scoped delegation is created:

```text
actor: codex
action: run_shell_command
target: pwd
max uses: 1
critical: true
```

The same MCP request is allowed once:

```text
classification: CRITICAL
decision: ALLOW
approval_method: DELEGATION
executed: true
output: ~/agent-sudo
```

A repeated request is denied:

```text
classification: CRITICAL
decision: DENY
executed: false
reason: delegation token is exhausted
```

Run with approvals and audit logging:

```bash
agent-sudo run examples/demo_requests.json --audit-log .agent-sudo/audit.jsonl
```

Initialize local approval hardening:

```bash
agent-sudo init-approval
```

Critical actions require the configured local approval passphrase.

Check local readiness:

```bash
agent-sudo doctor
```

Print dry-run setup guidance for an agent runtime:

```bash
agent-sudo setup codex
agent-sudo setup claude-desktop
```

Agent installation guidance:

- [Install For Agents](docs/INSTALL_FOR_AGENTS.md)
- [Agent Install Prompt](docs/AGENT_INSTALL_PROMPT.md)
- [Enforcement Model](docs/ENFORCEMENT_MODEL.md)
- [Universal Schema](docs/UNIVERSAL_SCHEMA.md)
- [Integrations](docs/INTEGRATIONS.md)

## Do Not Commit Local State

Do not commit personal policy, auth files, audit logs, delegation files, approval config, or local runtime config.
Keep local state under ignored paths such as `.agent-sudo/` or `~/.agent-sudo/`.

Never commit:

- personal policy files
- auth files
- audit logs
- local approval config
- delegation state
- environment files
- credentials, tokens, or secrets

## Request Format

Each request is a JSON object:

```json
{
  "actor": "codex",
  "source": "user",
  "source_trust": "USER_DIRECT",
  "tool": "filesystem",
  "action": "read_file",
  "target": "README.md",
  "payload_summary": "Read project documentation",
  "risk_hints": ["local_file"]
}
```

The input file may contain either one request object or a list of request objects.

Supported `source_trust` values:

- `USER_DIRECT`
- `AGENT_INTERNAL`
- `EXTERNAL_CONTENT`
- `UNKNOWN`

## Provenance

Requests can include structured provenance so the gateway can distinguish direct user intent from agent-internal work and untrusted outside content.

```json
{
  "provenance": {
    "origin_type": "USER_DIRECT",
    "channel": "cli",
    "authenticated": true,
    "authentication_method": "local_session",
    "session_id": "session-example",
    "request_id": "request-example",
    "parent_request_id": "",
    "delegation_chain": []
  }
}
```

Origin types:

- `USER_DIRECT`
- `LOCAL_UI`
- `AGENT_INTERNAL`
- `EXTERNAL_CONTENT`
- `EXTERNAL_API`
- `UNKNOWN`

Channels:

- `cli`
- `desktop_app`
- `browser`
- `email`
- `webpage`
- `api`
- `mcp`
- `unknown`

Policy behavior:

- authenticated `USER_DIRECT` requests can proceed to approval
- `EXTERNAL_CONTENT` can never approve or escalate itself
- `UNKNOWN` sensitive or critical actions require approval
- external content asking for tool use is blocked unless a user explicitly delegates the matching scope

Provenance is written to audit logs, including `request_id`, `parent_request_id`, and `delegation_chain`.

## Default Policy

SAFE actions are auto-allowed by default:

- `read_file` (upgraded to `BLOCKED` if the target is a sensitive configuration, credential, token, auth, or runtime file)
- `search_files`
- `summarize`
- `draft`
- `analyze`

SENSITIVE actions require yes/no approval:

- `write_file`
- `edit_file`
- `create_cron`
- `send_message`
- `browser_click`

`write_file` and `edit_file` stay `SENSITIVE` for ordinary documents. They are upgraded to `CRITICAL` when the target is executable code, shell startup files, launchd plists, cron files, systemd units, MCP configs, or runtime configs.

CRITICAL actions require passphrase confirmation:

- `run_shell_command`
- `send_email`
- `delete_file`
- `money_transfer`
- `legal_or_employment_message`
- `credential_access`
- `external_post`

BLOCKED actions are denied by default:

- `exfiltrate_secrets`
- `disable_audit`
- `bypass_policy`
- `send_tokens`
- `destructive_recursive_delete`
- `modify_policy_without_approval`
- `delete_audit_log`
- `edit_agent_sudo_source`
- `modify_auth`
- `prompt_injection_attempt`

## Audit Log

Audit entries are JSONL records with:

- timestamp
- request
- classification
- decision
- approval method
- reason
- dry-run flag
- previous hash
- entry hash
- approval attempts

Example:

```json
{"timestamp":"2026-05-24T12:00:00Z","request":{"actor":"codex"},"classification":"SAFE","decision":"ALLOW","approval_method":"none","reason":"SAFE actions are allowed by policy","dry_run":true,"previous_hash":"0000000000000000000000000000000000000000000000000000000000000000","entry_hash":"..."}
```

Verify an audit log hash chain:

```bash
agent-sudo verify-audit .agent-sudo/audit.jsonl
```

## Approval Hardening

Sensitive actions use `CLI_CONFIRM`.
Critical actions use `PASSPHRASE_CONFIRM`.

Initialize the local approval passphrase before approving critical actions:

```bash
agent-sudo init-approval
```

This writes a local config file at:

```text
~/.agent-sudo/config.json
```

The raw passphrase is never stored.
`agent-sudo` stores only a PBKDF2-HMAC-SHA256 hash with a random salt and iteration count.

Critical actions require the passphrase because a simple `yes` prompt can be typed by the wrong process, a compromised terminal session, or an automation wrapper.
The passphrase is intended to prove that the local user is actively approving a high-risk action at that moment.

Do not reuse any banking, email, source-control, work, or personal account password.
Use a unique local approval phrase for `agent-sudo`.

Non-interactive behavior is conservative:

- if there is no TTY, approval prompts are not shown
- approval-required decisions remain pending as `REQUIRE_APPROVAL` or `REQUIRE_STRONG_APPROVAL`
- tools do not execute unless the final gateway decision is `ALLOW`
- daemon, cron, and background runs never auto-approve

External content cannot approve or initiate tool execution for itself.
If a request with `EXTERNAL_CONTENT` trust needs approval, the gateway denies that runtime execution path instead of asking the external content to confirm anything.

Approval attempts are included in the audit log with method, result, pending state, and reason.

## Scoped Delegation

Scoped delegation lets a local user grant a temporary, narrow permission without blanket approval.
Delegation records are local JSON, stored by default at:

```text
~/.agent-sudo/delegations.json
```

Delegation token IDs are random UUIDs.
The token body contains no secrets; it is a local policy record with actor, action, path, expiry, use count, and reason.

Create a delegation:

```bash
agent-sudo delegate create \
  --actor agent-a \
  --allow-action read_file \
  --allow-path ~/example/project-files \
  --ttl-seconds 7200 \
  --max-uses 50 \
  --reason "Agent can read project files for 2 hours"
```

Allow Codex to edit only this README:

```bash
agent-sudo delegate create \
  --actor codex \
  --allow-action edit_file \
  --allow-path /home/user/agent-sudo/README.md \
  --ttl-seconds 3600 \
  --max-uses 5 \
  --reason "Codex can edit agent-sudo README"
```

List delegations:

```bash
agent-sudo delegate list
```

Revoke a delegation:

```bash
agent-sudo delegate revoke TOKEN_ID
```

Matching rules:

- actor must match
- action must be in `allowed_actions`
- target path must match `allowed_paths`
- action must not be in `denied_actions`
- token must not be expired, revoked, or exhausted
- usage count increments after successful delegated use

Critical actions still require strong approval unless the delegation was created with `--critical`.
Use that sparingly. For example, do not delegate email sending unless the local user explicitly wants that scope:

```bash
agent-sudo delegate create \
  --actor codex \
  --allow-action send_email \
  --allow-path recipient@example.invalid \
  --critical \
  --max-uses 1 \
  --reason "One explicitly approved email"
```

### Delegation Troubleshooting

If a request fails to match any delegation, `agent-sudo` returns a detailed diagnostic reason instead of a generic mismatch. This details:
- **actor mismatch**: includes expected vs actual actor.
- **action mismatch**: includes expected vs actual allowed actions.
- **path mismatch**: includes expected path scope vs actual target path.
- **critical flag missing**: if the request is critical but the token lacks the critical flag.
- **expired, revoked, or exhausted**: if the token's lifetime or uses have been exceeded, or it has been explicitly revoked.

> [!NOTE]
> Standard MCP clients (such as Claude Desktop or Cursor) connect using the default actor `mcp-client`. Ensure your delegation tokens match `mcp-client` as the `--actor` argument, or match the exact actor name specified in the incoming `ActionRequest`.

## Tamper Resistance

`agent-sudo` treats attempts to weaken the gateway itself as high-risk.
Any write, edit, delete, shell, auth, or cron action targeting protected paths is upgraded to `CRITICAL`, unless the action is explicitly blocked.

Protected targets include:

- `agent_sudo/config/*`
- `~/.agent-sudo/*`
- `~/.agent-runtime/auth.json`
- `~/.agent-runtime/*`
- audit log files
- policy YAML files
- `pyproject.toml`
- `agent_sudo/**/*.py`
- executable scripts such as `*.sh`, `*.bash`, `*.zsh`, `*.py`, `*.js`, `*.ts`, `*.rb`, and `*.pl`
- shell startup files such as `.zshrc` and `.bashrc`
- launchd plists, cron files, and systemd units
- MCP and runtime configuration files

Specific tamper actions are blocked by default:

- `disable_audit`
- `modify_policy_without_approval`
- `delete_audit_log`
- `edit_agent_sudo_source`
- `modify_auth`

Audit logs are hash-chained. Each JSONL entry includes:

- `previous_hash`
- `entry_hash`

The entry hash is:

```text
sha256(previous_hash + canonical_json(entry_without_entry_hash))
```

This does not make local files impossible to delete or replace. It makes after-the-fact tampering detectable when a verifier has access to the log file.

## Prompt Injection Handling

External content is treated as untrusted data, never as instructions.
Every `ActionRequest` carries a `source_trust` value:

- `USER_DIRECT`: direct human instruction
- `AGENT_INTERNAL`: agent-generated internal step
- `EXTERNAL_CONTENT`: webpage, email, document, chat, issue, or other outside text
- `UNKNOWN`: missing or unclear provenance

For `EXTERNAL_CONTENT` and `UNKNOWN`:

- safe actions are raised to approval-required tool use
- sensitive actions still require approval
- critical actions still require strong approval
- blocked actions remain denied
- obvious instruction-override phrases are denied before execution

The phrase detector catches obvious malicious instructions such as:

- `ignore previous instructions`
- `reveal secrets`
- `send tokens`
- `disable security`
- `bypass policy`
- `run this command`
- `exfiltrate`
- `system prompt`
- `developer message`

Detected phrases are classified as `prompt_injection_attempt` behavior and result in `BLOCKED`.
This detector is not a security boundary, not a parser, and not a complete content-security system. It is a convenience catch for obvious malicious instructions.

The security boundary is:

- provenance attached to the `ActionRequest`
- policy classification and decision logic
- mandatory routing of native tool calls through `PermissionGateway.evaluate()`

If an agent can bypass `agent-sudo` and call tools directly, phrase detection cannot protect those calls.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full execution path.

## Adapter Stubs

The example agent adapters normalize simple dictionaries into `ActionRequest` objects.
They are intentionally thin so agent runtimes can integrate without giving the gateway access to secrets or tool execution internals.

## How to Integrate with Agent Runtimes

The enforced boundary is:

1. Build an `ActionRequest`.
2. Pass it to `SafeToolExecutor`.
3. Let `SafeToolExecutor` call `PermissionGateway.evaluate()`.
4. Execute the real tool only when the final gateway decision is `ALLOW`.

Do not let any agent runtime call sensitive tools directly.
The runtime adapter should translate tool intent into an explicit request, then hand that request to the safe executor.

Native adapter entrypoints provide the intended path:

```python
from agent_sudo.adapters.codex import execute_codex_tool_call
from agent_sudo.adapters.hermes import execute_hermes_tool_call

codex_result = execute_codex_tool_call(codex_tool_call_dict, safe_executor)
hermes_result = execute_hermes_tool_call(hermes_tool_call_dict, safe_executor)
```

For inspection without execution:

```python
from agent_sudo.adapters.codex import from_codex_tool_call
from agent_sudo.adapters.hermes import from_hermes_tool_call

codex_request = from_codex_tool_call(codex_tool_call_dict)
hermes_request = from_hermes_tool_call(hermes_tool_call_dict)
```

Common native actions are normalized before policy evaluation:

- terminal or shell calls become `run_shell_command`
- `write_file`, `patch`, and `edit` calls become `write_file` or `edit_file`
- `read_file` calls become `read_file`
- browser or computer-use clicks become `browser_click`
- email and messaging sends become external communication actions
- auth edits become `modify_auth`
- cron jobs become `create_cron`
- unknown native tool calls become `unknown_tool_call`, which is `SENSITIVE` by default and requires approval

Example:

```python
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.audit import AuditLogger
from agent_sudo.builders import AgentActionRequest
from agent_sudo.executors import SafeToolExecutor, ShellCommandExecutor
from agent_sudo.gateway import PermissionGateway
from agent_sudo.policy import load_default_policy

policy = load_default_policy()
gateway = PermissionGateway(
    policy,
    approvals=ApprovalProvider(),
    audit_logger=AuditLogger(Path(".agent-sudo/audit.jsonl")),
)

shell = ShellCommandExecutor(allowed_commands={"echo", "pwd", "python3"})
safe_shell = SafeToolExecutor(gateway, shell)

request = AgentActionRequest.shell_command(
    "python3 -m unittest discover -s tests",
    actor="codex",
    source="user",
)

result = safe_shell.execute(request)
if not result.executed:
    print(result.reason)
```

Builder helpers are available for common agent actions:

- `AgentActionRequest.shell_command(...)`
- `AgentActionRequest.file_read(...)`
- `AgentActionRequest.file_write(...)`
- `AgentActionRequest.file_edit(...)`
- `AgentActionRequest.file_delete(...)`
- `AgentActionRequest.browser_click(...)`
- `AgentActionRequest.send_message(...)`
- `AgentActionRequest.send_email(...)`
- `AgentActionRequest.modify_auth(...)`
- `AgentActionRequest.create_cron(...)`

The shell executor also has a local defense-in-depth layer.
It executes nothing unless the command name is explicitly allowlisted.
Even after gateway approval, it blocks dangerous command shapes such as recursive deletes, network-capable commands, auth-file permission changes, and obvious token or credential exfiltration patterns.

## Development

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run a sample dry-run:

```bash
python3 -m agent_sudo.gateway run examples/demo_requests.json --dry-run
```
