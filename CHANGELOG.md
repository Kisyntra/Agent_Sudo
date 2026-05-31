# Changelog

## v0.4.1

- Adds `agent-sudo audit list`, a human-readable view of the audit log. Renders each record as a table (time, decision, actor, action, target, reason) so users can review what an agent did without parsing raw JSONL or writing code. Supports `--limit N` (default 20; `0` for all) and `--json`, defaults to the MCP server log at `.agent-sudo/mcp-audit.jsonl`, and handles both gateway-decision records and approval lifecycle events. Complements the existing integrity-only `verify-audit`.
- Adds `agent-sudo workspace set <path>` and `agent-sudo workspace show` so Claude Desktop users can persist the fixed workspace once in `~/.agent-sudo/config.json` and omit `--workspace` from the MCP server config.
- Fixes `agent-sudo doctor` for installed package users by running the contributor-only personal-data scan only when the source-tree scanner exists.
- Updates Claude Desktop onboarding docs and README setup guidance to make workspace persistence, audit verification, and native-tool bypass boundaries explicit.

## v0.4.0

First stable public release of the `agent-sudo` local permission gateway for AI agent tool execution.

- Consolidates release candidate iterations (rc1 through rc14) into the first stable production-ready release.
- Features robust security boundaries, including:
  - Deep-scanning of shell command arguments to block path traversal, nested subshells, symlinks, and utility bypasses targeting protected configurations.
  - PBKDF2-HMAC-SHA256 passphrase-based confirmation gating for sensitive and critical actions.
  - Tamper-resistant, cryptographically secured SHA-256 hash-chained JSONL audit logs.
  - Scoped, TTL-limited, and use-quota restricted temporary delegation tokens.
- Introduces native macOS user notifications and apple-script based auto-opening Terminal approval-helper utilities.
- Implements standard stdio Model Context Protocol (MCP) server integration (`agent-sudo-mcp`) out of the box with Claude Desktop and Cursor.
- Includes a complete python packaging structure with zero external runtime dependencies.

## v0.4.0-rc14

Release candidate addressing critical shell command policy bypass vulnerabilities.

- Hardens `is_blocked_shell_target` in `agent_sudo/classifier.py` and `agent_sudo/executors.py` by implementing comprehensive substring inspections for protected configuration paths and files (e.g. `.agent-sudo`, `.ssh`, `.agent-runtime`, `.env`, `auth.json`, `policy.yaml`, etc.).
- Adds deep token scanning to check all flattened command arguments for symlinks pointing to protected configuration paths, preventing obfuscation-based bypasses.
- Introduces robust regression tests covering path traversal variations (`$HOME`, relative `../`, no-space redirections `>`), copy/move/link utilities (`mv`, `cp`, `ln`, `rsync`, `tar`, `tee`, `dd`, `cat`), logical chained commands (`&&`, `;`), nested subshells (`bash -c`), and symlinks.

## v0.4.0-rc13

Release candidate introducing portable audit verifier helpers.

- Implements stable PolicyDecision and AuditRecord schemas.
- Adds canonical hash-chain verification semantics.
- Introduces `agent-sudo verify-audit` command-line utility to cryptographically validate audit trails and detect tamper attempts.
- Publishes lightweight `agent_sudo.spec_helpers` module for third-party runtime integrations.

## v0.4.0-rc12

Release candidate polishing the guided terminal helper auto-open UX for Claude Desktop approval workflows.

- Cleans and clears the terminal screen immediately upon auto-open to suppress login shell warnings, powerlevel10k details, and startup noise.
- Sanitizes and truncates target details to command/file basenames (e.g. `python3` instead of `/usr/bin/python3`) to reduce shell/path leakage and secrets exposure.
- Implements a 3-second auto-close countdown on successful approval or denial when a single pending request is resolved.
- Ensures keep-open behavior (blocking on a "Press Enter to exit..." prompt) on onboarding states, multiple requests, wrong passphrases, watch mode, or unexpected execution failures.
- Polishes overall operator UX and visual presentation for auto-opened helper sessions.

## v0.4.0-rc11

Release candidate introducing guided terminal helper workflow for pending approvals.

- Added `agent-sudo approval-helper` CLI command to guide the user interactively through approvals or denials with onboarding tips and interactive `[y/N]` prompts.
- Added continuous watching support via `--watch` flag for `approval-helper`.
- Added optional macOS Terminal.app auto-opening window support to streamline developer and Claude Desktop testing workflows.
- Wired `--open-approval-terminal` configuration flag to MCP server (`agent-sudo-mcp`) and CLI evaluation paths.
- Enabled environment variable support via `AGENT_SUDO_OPEN_APPROVAL_TERMINAL=1`.
- Built secure AppleScript Terminal opening execution (safely using python's `sys.executable` and `shlex.quote` without passing secrets, sensitive command targets, or passphrases).
- Ensured non-blocking opener behavior (opener warning logged to stderr on failure).
- Maintained exact approval validation, `shell=False` protections, and auto-approval security boundaries.

## v0.4.0-rc10

Release candidate introducing optional native macOS approval notifications.

- Added optional native macOS desktop notification support for pending approval requests.
- Added `--notify` CLI flag to both `agent-sudo-mcp` and `agent-sudo run / generic-run` commands.
- Enabled environment variable `AGENT_SUDO_NOTIFY=1` to toggle notifications.
- Sanitized and truncated notification payloads (reducing path disclosures and command arguments) to prevent secrets leakage.
- Ensured non-blocking notification behavior; failures do not disrupt the approval creation or MCP tool execution.
- Validated Claude Desktop end-to-end approval UX flow.
- Avoided the use of `shell=True` to prevent shell injection vectors.

## v0.4.0-rc9

Release candidate adding configurable workspace root support.

- Added CLI flags `--workspace` to both `agent-sudo context` and `agent-sudo-mcp` tools.
- Added environment variable support via `AGENT_SUDO_WORKSPACE`.
- Added config file fallback loading workspace paths from `~/.agent-sudo/config.json`.
- Introduced `configured_workspace` and `effective_workspace` fields to the runtime context.
- Prevents unanchored root execution reports for MCP clients (like Claude Desktop) when a valid workspace is configured.
- Maintained exact approval mechanics and policy boundaries for all workspace contexts.

## v0.4.0-rc8

Release candidate focusing on post-upgrade verification privacy and hygiene fixes.

- Redacted absolute paths from the `passphrase_reset` audit event to avoid recording raw personal user directories.
- Excluded the `.agent-sudo/` runtime state directory and build artifacts from the personal-data hygiene checks.
- Prevented `agent-sudo doctor` and post-upgrade verification from failing on local runtime audit log files.
- Preserved all local runtime state and audit log hash chains intact.

## v0.4.0-rc7

Release candidate introducing workspace discovery and runtime context for MCP clients.

- Added runtime context discovery utility to detect cwd, repo root, git branch, root execution, and workspace presence.
- Added `agent-sudo context` CLI command to output workspace context as JSON.
- Added `get_runtime_context` MCP tool to return the same structured context to MCP clients.
- Classifies context retrieval as `SAFE` (read-only, no approval required).
- Logs warnings to `stderr` when running from the filesystem root or when no git repository/workspace is detected.

## v0.4.0-rc6

Release candidate focused on improving CLI approval failure visibility.

- Failed `agent-sudo approve` now prints clear errors to `stderr` explaining the failure reason.
- Wrong passphrase no longer prints misleading pending approval JSON to `stdout`.
- Expired approval failure is clearly reported to the user.
- Successful approvals still print the updated `APPROVED` JSON to `stdout` and exit `0`.
- No changes to underlying approval security semantics.

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
