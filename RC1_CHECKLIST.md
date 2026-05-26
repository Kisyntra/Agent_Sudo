# agent-sudo v0.4.0-rc3 Release Candidate Checklist

This checklist outlines the verification steps required to certify `agent-sudo` for the `v0.4.0-rc3` release candidate.

---

## 1. Documentation Verification & Link Checks

Verify that the following documentation files exist, contain no dead links, and link to the correct resource targets:

- [x] **[README.md](file:///Volumes/Storage/Agent_Sudo/README.md)**
  - [x] Links to [docs/UPGRADE.md](file:///Volumes/Storage/Agent_Sudo/docs/UPGRADE.md)
  - [x] Links to [docs/FIRST_RUN.md](file:///Volumes/Storage/Agent_Sudo/docs/FIRST_RUN.md)
  - [x] Links to [docs/ARCHITECTURE.md](file:///Volumes/Storage/Agent_Sudo/docs/ARCHITECTURE.md)
- [x] **[docs/FIRST_RUN.md](file:///Volumes/Storage/Agent_Sudo/docs/FIRST_RUN.md)**
  - [x] Links to [docs/ARCHITECTURE.md](file:///Volumes/Storage/Agent_Sudo/docs/ARCHITECTURE.md)
- [x] **[docs/UPGRADE.md](file:///Volumes/Storage/Agent_Sudo/docs/UPGRADE.md)**
  - [x] Explains `upgrade-local` and manual upgrade paths.
- [x] **[docs/MCP_SERVER_SETUP.md](file:///Volumes/Storage/Agent_Sudo/docs/MCP_SERVER_SETUP.md)**
  - [x] Correctly lists configurations for Cursor and Claude Desktop.
- [x] **[docs/END_TO_END_DEMO.md](file:///Volumes/Storage/Agent_Sudo/docs/END_TO_END_DEMO.md)**
  - [x] Correctly shows the standard deny-to-allow flow.
- [x] **[docs/ARCHITECTURE.md](file:///Volumes/Storage/Agent_Sudo/docs/ARCHITECTURE.md)**
  - [x] Details the pipeline from `ActionRequest` to execution.

---

## 2. Command Exist & Help Checks

Confirm that every subcommand is active and displays correct instructions under `--help`:

- [x] `agent-sudo --help`
- [x] `agent-sudo --version`
- [x] `agent-sudo doctor`
- [x] `agent-sudo init-approval`
- [x] `agent-sudo check --help`
- [x] `agent-sudo run --help`
- [x] `agent-sudo approvals list --help`
- [x] `agent-sudo approve --help`
- [x] `agent-sudo deny --help`
- [x] `agent-sudo delegate create --help`
- [x] `agent-sudo delegate list --help`
- [x] `agent-sudo delegate revoke --help`
- [x] `agent-sudo verify-audit --help`
- [x] `agent-sudo upgrade-local --help`
- [x] `agent-sudo-mcp --help`
- [x] `agent-sudo-mcp --version`

---

## 3. Example Code & Demo Validation

Check that every tutorial example runs and generates correct outputs:

- [x] **passphrase setup**: `agent-sudo init-approval` prompts for and saves passphrase hash correctly.
- [x] **doctor diagnostics**: `agent-sudo doctor` outputs warnings and status for configuration paths.
- [x] **check command**: `agent-sudo check examples/demo_requests.json` prints decisions correctly.
- [x] **dry-run mode**: `agent-sudo run examples/demo_requests.json --dry-run` successfully parses.
- [x] **delegation creation**: `agent-sudo delegate create` correctly sets actor, allowed actions, paths, and limits.
- [x] **E2E verification script**: The subprocess test execution in `docs/FIRST_RUN.md` runs and returns correct exit statuses.

---

## 4. Stale Reference Cleanups

Verify that there are no obsolete artifacts or configurations in source control:

- [x] **No LSP framing references**: Standard stdio newline transport replaces all old Content-Length headers references.
- [x] **No stale version references**: Active release labels should be updated to `v0.4.0-rc3` (or package version `0.4.0rc3`) before release.
- [x] **No uncommitted local tests**: No scratch scripts or temporary audit files (`.agent-sudo/audit.jsonl`, etc.) exist in the tracked workspace.

---

## 5. Security & Isolation Controls

Verify that security defaults are actively verified by testing:

- [x] **Protected file reads**: Target paths like `~/.ssh/config` or `.env` are classified as `BLOCKED` and denied.
- [x] **Tamper upgrades**: Changes to codebase scripts or configuration files upgrade the evaluation to `CRITICAL`.
- [x] **Passphrase locking**: 3 failed critical prompts trigger immediate lockout for 5 minutes.
- [x] **Uninitialized warnings**: Running `approve` or creating a pending approval without running `init-approval` prints the onboarding warn dialog on `sys.stderr`.
- [x] **Audit integrity**: Verifying audit logs with `agent-sudo verify-audit` detects tampering or signature modifications correctly.
