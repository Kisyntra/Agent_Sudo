# Commit Plan

## Working Tree Groups

### Demo/docs from previous work

- `README.md`
- `RELEASE_REPORT_V0_2_0.md`
- `DEMO_TRANSCRIPT.md`
- `docs/END_TO_END_DEMO.md`
- `docs/MCP_SERVER_SETUP.md`
- `tests/test_end_to_end_delegation_flow.py`

### Pending approvals feature

- `agent_sudo/audit.py`
- `agent_sudo/gateway.py`
- `agent_sudo/mcp_server.py`
- `agent_sudo/mcp_validation.py`
- `agent_sudo/models.py`
- `agent_sudo/pending_approvals.py`
- `docs/PENDING_APPROVALS.md`
- `docs/MCP_SERVER_SETUP.md`
- `README.md`
- `tests/test_pending_approvals.py`

### Unrelated changes

- None found in the current working tree.

## Files To Commit

Commit the pending approvals workflow and the supporting demo/docs updates together if releasing as the next beta:

- `README.md`
- `RELEASE_REPORT_V0_2_0.md`
- `DEMO_TRANSCRIPT.md`
- `agent_sudo/audit.py`
- `agent_sudo/gateway.py`
- `agent_sudo/mcp_server.py`
- `agent_sudo/mcp_validation.py`
- `agent_sudo/models.py`
- `agent_sudo/pending_approvals.py`
- `docs/END_TO_END_DEMO.md`
- `docs/MCP_SERVER_SETUP.md`
- `docs/PENDING_APPROVALS.md`
- `tests/test_end_to_end_delegation_flow.py`
- `tests/test_pending_approvals.py`

`COMMIT_PLAN.md` is a release-prep artifact. Do not include it in the product commit unless you want to preserve the release decision notes in the repo.

## Suggested Commit Message

```text
Add pending approvals for non-interactive MCP clients
```

## Suggested Tag

Use `v0.3.0-beta`.

Pending approvals are a new MCP workflow, not just a UX patch: non-interactive approval-required calls now create local approval requests, expose an approval ID/command to MCP clients, support explicit approve/deny CLI handling, and consume approved retries once.

## Release Notes

- Added local pending approvals for non-interactive MCP clients.
- Added MCP response fields for `approval_request_id` and `approval_command`.
- Added `agent-sudo approvals list`, `agent-sudo approve`, and `agent-sudo deny` workflow coverage.
- Added single-use retry semantics for approved pending requests.
- Added audit events for pending approval lifecycle changes.
- Documented non-interactive MCP limitations and retry behavior.
- Added end-to-end MCP delegation demo docs and regression tests.

## Risks And Limitations

- Pending approvals are local state in `~/.agent-sudo/pending_approvals.json` by default; this file can contain local action targets and payload summaries and must not be committed.
- Approval matching is action-based so clients may retry with a different JSON-RPC request ID, but the action must still match the pending request.
- Approved pending requests are single-use and transition to `USED`; later retries are blocked.
- Denied and expired pending requests cannot be reused.
- MCP protection only applies to calls routed through `agent-sudo-mcp`; direct access to shell, files, browser, email, or desktop tools can bypass agent-sudo.
- Critical approvals still require the locally configured passphrase.

## Verification

Passed:

```text
python3 scripts/check_no_personal_data.py
python3 -m unittest discover -s tests
git diff --check
```

Also verified that no `__pycache__`, `*.pyc`, local audit logs, local approval/delegation JSON, `.venv`, or temp files remain present after cleanup.
