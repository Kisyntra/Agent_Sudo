# agent-sudo v0.1.0 Release Report

## Project Summary

`agent-sudo` is a local permission gateway for AI agent tool execution.
It exists to make agent actions explicit, classify risk, enforce local policy, require approval when needed, and write auditable decisions before tools execute.

Release positioning:

- One local gateway. Any agent. Every tool call checked.
- Local-only MVP.
- No cloud service, database, web UI, or bundled credentials.
- Enforced only when tool execution is routed through `agent-sudo`.

## Architecture Summary

Core modules:

- `models.py`: request, provenance, approval, gateway result, and delegation data models.
- `policy.py`: YAML-backed action classification policy.
- `classifier.py`: risk classification, protected-path handling, trust/provenance behavior, and prompt-injection checks.
- `gateway.py`: CLI and `PermissionGateway` approval/delegation/audit orchestration.
- `executors.py`: safe execution boundary and shell executor defense-in-depth.
- `approvals.py`: CLI and passphrase approval flow with local PBKDF2 hash config.
- `audit.py`: JSONL audit log with hash chaining and verification.
- `delegations.py`: local scoped delegation token store.
- `adapters/`: native and universal tool-call normalization for common agent runtimes.
- `doctor.py` and `setup_guides.py`: local readiness checks and dry-run setup guidance.

## Feature List

- Permission gateway for local agent tool requests.
- YAML policy engine with `SAFE`, `SENSITIVE`, `CRITICAL`, and `BLOCKED` classes.
- Safe executor boundary before real tool execution.
- Shell executor allowlist and dangerous-command blocking.
- Native and universal adapters for multiple agent styles.
- Universal tool-call schema documentation.
- Tamper-resistant audit logs using hash chains.
- Audit verification CLI.
- Prompt-injection phrase detection.
- Trust levels and structured provenance model.
- Approval hardening with CLI confirmation and passphrase confirmation.
- Local PBKDF2-HMAC-SHA256 approval config.
- Scoped delegation tokens with expiry, max use count, actor/action/path matching, and revocation.
- Doctor command for local readiness.
- Dry-run setup checklist commands for agent integration.
- Personal-data scanner and open-source-safe fixture policy.

## Security Model

`agent-sudo` is a local enforcement layer.
It checks a normalized `ActionRequest` before a tool is allowed to execute.

Security controls:

- Least privilege by default.
- External content is treated as data, not instructions.
- Sensitive actions require approval.
- Critical actions require passphrase approval unless explicitly delegated with critical scope.
- External content cannot approve or escalate itself.
- Protected files and policy/audit paths are upgraded to critical or blocked.
- Known tamper actions are blocked.
- Audit entries are hash-chained.
- Delegations are scoped by actor, action, path, expiry, use count, and revocation.
- Local secrets and runtime state are ignored and documented as non-committable.

## Threat Model

Primary risks addressed:

- Prompt injection.
- Insecure or over-permissioned tools.
- Excessive agency.
- Missing human approval.
- Poor audit trails.
- Attempts to weaken policy, audit, approval, or source files.
- Unclear request provenance.
- Overbroad agent delegation.

Assumptions:

- The agent runtime can be configured to route tool calls through `agent-sudo`.
- Local files can be read and written by the user account.
- `agent-sudo` is not a full sandbox or OS-level access-control system.

## Limitations

- Cannot override an agent's system prompt.
- Cannot protect tools the agent can still access directly.
- Not a kernel sandbox, VM, container, or mandatory access-control system.
- Audit hash chains detect tampering but do not prevent local deletion or replacement.
- Prompt-injection detection is phrase-based and intentionally primitive.
- Setup commands are dry-run checklists; they do not edit agent runtime configs.
- Real integrations still need wrapper/proxy work in each agent runtime.
- `doctor` warns until `agent-sudo init-approval` is run.
- Direct system `pip install -e .` can fail on externally managed Python installs; virtualenv install works.

## Installation Methods

Documented install paths:

```bash
python3 -m pip install -e .
```

For externally managed Python installs:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e .
```

Run without installing:

```bash
python3 -m agent_sudo.gateway run examples/demo_requests.json --dry-run
```

Package metadata:

- Version: `0.1.0`
- License: `Apache-2.0`
- Console script: `agent-sudo`

## Integration Modes

SDK mode:

- Import `PermissionGateway`.
- Convert native tool calls to `ActionRequest`.
- Wrap tool execution with `SafeToolExecutor`.

CLI wrapper mode:

- Agent emits JSON.
- Wrapper calls `agent-sudo generic-check` or `agent-sudo generic-run`.
- Real execution proceeds only after an allowed gateway decision.

MCP/proxy mode:

- Proxy receives a native tool call.
- Proxy normalizes to universal schema.
- Proxy asks `agent-sudo` for a decision before forwarding.

Practical enforcement warning:

- If the agent keeps direct shell, browser, email, messaging, file-write, or credential access, `agent-sudo` is advisory, not enforced.

## Documentation Audit

Reviewed:

- `README.md`
- `CHANGELOG.md`
- `SECURITY.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `RELEASE_CHECKLIST.md`
- `docs/INSTALL_FOR_AGENTS.md`
- `docs/AGENT_INSTALL_PROMPT.md`
- `docs/ENFORCEMENT_MODEL.md`
- `docs/UNIVERSAL_SCHEMA.md`
- `docs/INTEGRATIONS.md`
- `examples/README.md`

Assessment:

- Documentation is coherent for v0.1.0.
- Commands shown in docs are either verified directly or intentionally interactive/advisory.
- Examples are consistent with the current schema and use fake actors, fake paths, and placeholder addresses.
- Release checklist includes the known externally managed Python install caveat.

## Command Validation

Required commands:

```text
python3 scripts/check_no_personal_data.py
Personal-data scan passed
```

```text
python3 -m unittest discover -s tests
Ran 69 tests
OK
```

Additional documented command checks:

- `python3 -m agent_sudo.gateway check examples/demo_requests.json`: passed.
- `python3 -m agent_sudo.gateway run examples/demo_requests.json --dry-run`: passed.
- `python3 -m agent_sudo.gateway hermes-check examples/hermes_tool_call.json`: passed.
- `python3 -m agent_sudo.gateway codex-check examples/codex_tool_call.json`: passed.
- `python3 -m agent_sudo.gateway generic-check examples/generic_tool_call.json`: passed.
- `python3 -m agent_sudo.gateway generic-run examples/generic_tool_call.json --dry-run`: passed.
- `python3 -m agent_sudo.gateway doctor`: passed with expected approval-config warning.
- `python3 -m agent_sudo.gateway setup codex`: passed.

Install check:

- `python3 -m pip install -e .`: blocked by externally managed Python environment.
- Virtual environment editable install: passed.

## Repository Hygiene

Checked for:

- Generated local artifacts.
- Personal names.
- Real home paths.
- Real service references.
- Real emails.
- Token key names.
- Stale `TODO`/`FIXME` markers.
- License mismatch.

Result:

- Generated local artifacts were removed.
- Personal-data scan passed.
- Prohibited-marker grep returned no findings.
- `pyproject.toml` license matches `LICENSE`.

## Readiness Scores

- Documentation: 8/10
- Testing: 8/10
- Security: 7/10
- Maintainability: 7/10
- User experience: 7/10
- Publish readiness: 8/10

Rationale:

- Documentation is strong for an MVP, but real runtime-specific setup still needs deeper guides.
- Tests cover core behavior well, but there is no packaging CI matrix yet.
- Security model is explicit and conservative, but enforcement depends on external routing.
- Code is small and modular, though CLI/gateway responsibilities could be split later.
- UX is understandable, but first-run approval setup and integration remain manual.

## Top 5 Post-v0.1.0 Improvements

1. Build real wrapper/proxy examples for one shell executor and one MCP-style tool.
   - Impact: very high
   - Effort: medium

2. Add CI for tests, personal-data scan, packaging, and docs command checks.
   - Impact: high
   - Effort: low

3. Split CLI command handling from `gateway.py` into a dedicated CLI module.
   - Impact: medium
   - Effort: low

4. Add signed audit checkpoints or external hash export.
   - Impact: high
   - Effort: medium

5. Add structured policy validation and richer YAML schema errors.
   - Impact: medium
   - Effort: low

## Publish Readiness Assessment

Recommendation: Publish as beta.

Why:

- The project is understandable, installable in a virtual environment, testable, and open-source safe.
- Core MVP behavior is covered by tests.
- Security limitations are clearly documented.
- The main gap is enforcement integration: without concrete wrappers/proxies, users must still wire their agent runtimes correctly.

Publish as `v0.1.0-beta` or clearly label the repository as an MVP beta until at least one complete real wrapper/proxy integration is included.
