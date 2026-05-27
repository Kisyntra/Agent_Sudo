# Troubleshooting Guide

This guide provides solutions for common issues encountered when setting up, running, or developing with `Agent_Sudo`.

---

## 1. Claude says `workspace_detected = false`

* **Symptom**: The agent runs `get_runtime_context` and reports that `workspace_detected` is `false`.
* **Likely Cause**: The `--workspace` parameter is missing from the Claude Desktop config args list, or points to an invalid directory.
* **Fix**: Edit `claude_desktop_config.json` and ensure `--workspace` is present and followed by a valid, absolute path to your project folder.
* **Command Examples**:
  Ensure your config contains:
  ```json
  "args": [
    ...
    "--workspace",
    "/path/to/your/project"
  ]
  ```

---

## 2. Claude says running from `/`

* **Symptom**: The agent reports that the current working directory (`cwd`) is `/` (the root filesystem).
* **Likely Cause**: Claude Desktop spawns MCP servers in the root directory by default. Without a configured workspace, `Agent_Sudo` defaults its effective workspace to the process `cwd` (`/`).
* **Fix**: Configure `--workspace` in `claude_desktop_config.json` (see above) or define the `AGENT_SUDO_WORKSPACE` environment variable in the environment where Claude is run.
* **Command Examples**:
  To verify context resolution from the command line:
  ```bash
  agent-sudo context --workspace /path/to/your/project
  ```

---

## 3. `agent-sudo-mcp` exits: `error: argument --workspace: expected one argument`

* **Symptom**: The MCP server fails to start, and Claude Desktop logs show `agent-sudo-mcp: error: argument --workspace: expected one argument`.
* **Likely Cause**: The `--workspace` argument and its path value are combined in a single JSON string in the configuration `args` list, or the path string is missing entirely.
* **Fix**: Ensure `--workspace` and the directory path are formatted as two distinct, separate elements in the JSON array.
* **Command Examples**:
  * **Incorrect**: `["--workspace /path/to/your/project"]`
  * **Correct**: `["--workspace", "/path/to/your/project"]`

---

## 4. Approval Expired

* **Symptom**: You approve a pending request in your terminal, but Claude Desktop still fails with a timeout or reports that the tool was not executed.
* **Likely Cause**: The default approval TTL (Time-to-Live) is 120 seconds. If you took longer than 2 minutes to run the approval command, the request expired and was automatically rejected.
* **Fix**: Ask Claude to retry the command to create a new pending approval, then approve it promptly. You can increase the TTL using the `--approval-ttl-seconds` flag or by setting the `AGENT_SUDO_APPROVAL_TTL_SECONDS` environment variable.
* **Command Examples**:
  Set TTL to 5 minutes (300 seconds) in Claude Desktop config:
  ```json
  "args": [
    ...
    "--approval-ttl-seconds",
    "300"
  ]
  ```

---

## 5. Passphrase Verification Failed

* **Symptom**: Running `agent-sudo approve <id>` fails with `Verification failed: incorrect passphrase`.
* **Likely Cause**: The passphrase entered does not match the salted PBKDF2 hash stored in `~/.agent-sudo/config.json`.
* **Fix**: Re-enter the passphrase carefully. If you have forgotten the passphrase, you must reset the approval configuration (see below).

---

## 6. Forgot Passphrase / Reset Approval Passphrase Safely

* **Symptom**: You cannot approve critical actions because you forgot your approval passphrase.
* **Likely Cause**: Passphrases are hashed using PBKDF2-HMAC-SHA256 and cannot be retrieved.
* **Fix**: Force-initialize a new passphrase. This will overwrite the previous configuration, cancel all pending approvals, and revoke any active delegations, but it will preserve your historical audit logs.
* **Command Examples**:
  To reset and set a new passphrase:
  ```bash
  agent-sudo init-approval --force
  ```

---

## 7. `upgrade-local` fails due to dirty tree

* **Symptom**: Running `agent-sudo upgrade-local` fails with `dirty working tree` or validation error.
* **Likely Cause**: The repository has modified or untracked files, and the upgrade script enforces clean repository states to prevent untracked/dirty changes from leaking into local upgrades.
* **Fix**: Commit your changes, stash them using Git, or clean untracked files before upgrading.
* **Command Examples**:
  ```bash
  # Check status
  git status
  # Stash local changes
  git stash -u
  # Run upgrade
  agent-sudo upgrade-local
  # Restore stashed changes
  git stash pop
  ```

---

## 8. `doctor` fails personal data scan

* **Symptom**: `agent-sudo doctor` fails with `FAIL: no personal data in repo`.
* **Likely Cause**: A local file inside the repository contains a personal identifier (like `/Users/username` or custom machine names).
* **Fix**: Scan for and remove or redact any occurrences of personal paths in your repository code, scripts, or examples, substituting them with generic placeholders like `/path/to/your/project`.
* **Command Examples**:
  Locate the offending files:
  ```bash
  python3 scripts/check_no_personal_data.py
  ```

---

## 9. Claude does not list `agent-sudo` tools

* **Symptom**: The tools `read_file`, `write_file`, `run_shell_command`, and `get_runtime_context` do not appear in Claude Desktop.
* **Likely Cause**: The MCP server failed to start, or Claude Desktop failed to connect. Common reasons include syntax errors in `claude_desktop_config.json`, or the executable path in the `command` field being incorrect.
* **Fix**: Check `claude_desktop_config.json` syntax. Inspect Claude Desktop's log files to find the startup crash logs.
* **Command Examples**:
  Verify the executable path works independently:
  ```bash
  /path/to/your/python/bin/agent-sudo-mcp --version
  ```
  Check Claude Desktop logs at:
  `~/Library/Logs/Claude/mcp.log` (or `mcp-server-agent-sudo.log`)

---

## 10. Multiple Python environments / Wrong executable

* **Symptom**: The CLI `agent-sudo` command works in your terminal, but Claude Desktop fails to launch `agent-sudo-mcp` or runs an older version.
* **Likely Cause**: Claude Desktop launches with a clean environment and might resolve a different Python interpreter or a different global path than your interactive terminal session.
* **Fix**: Avoid generic `agent-sudo-mcp` commands in Claude Desktop's `command` configuration. Instead, use the absolute path to the specific Python environment's binary.
* **Command Examples**:
  * **Incorrect**: `"command": "agent-sudo-mcp"`
  * **Correct**: `"command": "/path/to/agent-sudo-mcp" (or path to your virtualenv bin folder).

---

## 11. Pending approvals are stale

* **Symptom**: Running `agent-sudo pending` lists old, expired, or irrelevant requests.
* **Likely Cause**: Expired requests are kept in the pending store file until explicitly cleaned or overwritten by new requests.
* **Fix**: You can safely clear all pending approvals by removing the pending approvals file.
* **Command Examples**:
  ```bash
  rm ~/.agent-sudo/pending_approvals.json
  ```
