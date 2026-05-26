# Changelog

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
