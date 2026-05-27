# Changelog

## v0.4.0-rc5

Release candidate focused on secure passphrase reset flow.

- Implemented safe reset flow on `agent-sudo init-approval`: warns user, revokes active delegation tokens, and cancels active pending approvals (marking them `DENIED` with passphrase reset reason).
- Added CLI option overrides (`--config`, `--pending-approvals-file`, `--delegations-file`, `--audit-log`, and `--force`) for `init-approval` subcommand.
- Logged a chained `passphrase_reset` event to the audit log on successful reset.

## v0.4.0-rc4

Release candidate focused on approval lifecycle correctness.

- Fixed a bug where stale resolved approvals (`USED`, `EXPIRED`, `DENIED`) in the pending approvals JSON store incorrectly matched future identical requests and blocked them from executing.
- Ensured that future identical tool executions create a fresh pending approval request with a new unique UUID.
- Preserved single-use approval semantics, audit logging history, and local passphrase validation.
- Maintained all existing security boundaries, including `BLOCKED` policy enforcement and shell wrapper validation rules.

## v0.4.0-rc3

Release candidate focused on improving `upgrade-local` reliability with generated files.

- Added automatic cleaning of known generated untracked artifacts (like `agent_sudo.egg-info/`, `__pycache__/`, `.pytest_cache/`, `build/`, `dist/`, `.DS_Store`) during upgrade.
- Reduced friction for non-technical users upgrading editable installs by preventing build/test artifacts from blocking the upgrade.
- Bounded artifact cleanup strictly to known paths inside the repository root.
- Ensured unknown untracked files and tracked modified files continue to safely block upgrades by default.
- Maintained explicit requirement for `--allow-dirty` to ignore blocking user modifications.
- Kept configuration data, pending approvals, delegations, and audit logs under `~/.agent-sudo` completely untouched and preserved.

## v0.4.0-rc2

Release candidate focused on MCP approval lifecycle reliability and Claude Desktop usability.

- Changed pending approval TTL defaults to 120 seconds
- Added bounded TTL configuration through `AGENT_SUDO_APPROVAL_TTL_SECONDS` and `agent-sudo-mcp --approval-ttl-seconds`
- Added structured MCP approval metadata with approval ID, expiry, risk, action summary, and approval command
- Added `agent-sudo pending` for active pending approval review
- Added short-index approval support with `agent-sudo approve 1`
- Preserved exact-request matching, single-use approvals, audit logging, BLOCKED policy behavior, `.env` protections, and shell policy enforcement

## v0.2.0-beta

Beta release for the real MCP enforcement path.

- Added `agent-sudo-mcp` stdio MCP server
- Exposed MCP tools for `read_file`, `write_file`, and `run_shell_command`
- Routed MCP tool calls through `MCPGateway` and `PermissionGateway`
- Made shell execution `CRITICAL` by default
- Added path policy checks for demo writes and protected local paths
- Added approval lockout after repeated failed critical approvals
- Added MCP server setup and real-world validation docs
- Added subprocess integration tests for MCP initialize, tool listing, allowed reads, denied shell, and audit logging

## v0.1.0

Initial MVP release.

- Local permission gateway for agent tool requests
- YAML-backed policy engine
- Safe executor boundary before tool execution
- Agent adapters and universal tool-call schema
- Tamper-resistant JSONL audit logs
- Prompt-injection defense primitives
- Approval hardening with local passphrase hash
- Scoped delegation tokens
- Request provenance model
- Setup and doctor commands
