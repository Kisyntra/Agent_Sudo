# Claude Desktop Setup Guide

This guide explains how to install `Agent_Sudo`, connect it to Claude Desktop as a Model Context Protocol (MCP) server, and validate the setup.

## A. Prerequisites

Before starting, ensure you have:
- **Python 3.10 or higher** installed.
- **Claude Desktop** installed on macOS.
- **Terminal access** to run setup and approval commands.

---

## B. Installation and Upgrades

### Standard Installation
Install the package using `pip`:
```bash
pip install agent-sudo
```

### Developer / Editable Installation
If running from a local checkout or developing changes:
```bash
git clone <repository_url>
cd agent-sudo
pip install -e .
```

To verify the installation path and active environment:
```bash
which agent-sudo
agent-sudo --version
```

---

## C. Initialize Approval Passphrase

To approve critical actions (such as running shell commands), you must configure a local approval passphrase:

```bash
agent-sudo init-approval
```

> [!WARNING]
> - **The passphrase cannot be recovered.**
> - **Resetting the passphrase** will revoke all existing delegations and cancel any pending approvals.
> - **Audit logs are preserved** during a passphrase reset.

---

## D. Find Executable Path

Claude Desktop requires the absolute path to the `agent-sudo-mcp` executable. Locate it by running:

```bash
which agent-sudo-mcp
```
*(Example output: `/path/to/your/python/bin/agent-sudo-mcp`)*

Verify that the MCP server version is correct:
```bash
agent-sudo-mcp --version
```

---

## E. Claude Desktop Configuration

Claude Desktop reads its MCP server configuration from a local JSON file. 

1. Open the configuration file at:
   `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add `agent-sudo` to the `mcpServers` object:

```json
{
  "mcpServers": {
    "agent-sudo": {
      "command": "/path/to/agent-sudo-mcp",
      "args": [
        "--audit-log",
        "/path/to/mcp-audit.jsonl",
        "--pending-approvals-file",
        "/path/to/pending_approvals.json",
        "--workspace",
        "/path/to/project",
        "--notify",
        "--open-approval-terminal"
      ]
    }
  }
}
```

> [!IMPORTANT]
> - **Separate arguments**: Each command line flag and its value must be specified as a **separate** JSON string in the `args` array (e.g. write `"--workspace"` and `"/path/to/project"` as separate items).
> - **Workspace Config**: Always configure the `--workspace` parameter to point to a valid, absolute directory on your filesystem where you plan to execute commands. Claude Desktop launches MCP servers from the root `/` directory by default, so omitting the workspace will cause context detection to fail.
> - **Desktop Notifications**: Enabling `"--notify"` in `args` (or setting the environment variable `AGENT_SUDO_NOTIFY=1` before launching Claude) allows `Agent_Sudo` to trigger a native macOS user notification (using `osascript`) whenever an approval request is generated, warning the operator to run `agent-sudo pending` without having to poll the terminal constantly.
>   - **Optional & Default OFF**: Notifications must be explicitly enabled using the flag or environment variable.
>   - **macOS-only**: This is currently macOS-only MVP behavior.
>   - **Non-blocking & Safe**: If a notification fails to trigger or display, the operation will proceed normally without blocking approval creation or failing the MCP execution.
> - **Auto-Open Guided Terminal**: Enabling `"--open-approval-terminal"` in `args` (or setting the environment variable `AGENT_SUDO_OPEN_APPROVAL_TERMINAL=1`) automatically opens a new macOS Terminal.app window running `agent-sudo approval-helper` when a pending approval request is generated.
>   - **Optional & Default OFF**: This is disabled by default.
>   - **macOS-only**: Spawning a terminal window automatically is currently macOS-only behavior.
>   - **Non-blocking & Safe**: Spawning failure will fail safe, writing a warning to stderr without blocking tool execution or approval creation. It never auto-approves, never requests automated passphrases, and never passes sensitive payloads.

---

## F. Restart Claude Desktop

When configuration files are modified, you must fully terminate Claude Desktop and any cached background MCP servers to apply changes.

Run these commands on macOS:
```bash
# Terminate Claude Desktop
pkill -f Claude

# Kill any orphaned agent-sudo-mcp processes
pkill -f agent-sudo-mcp
```

Reopen Claude Desktop from your Applications folder.

---

## G. Validation Prompts

You can test that `Agent_Sudo` is working correctly by sending the following prompts to Claude.

### Validation Prompt 1: Context Detection
> **Prompt**: Using agent-sudo only, call get_runtime_context and tell me the runtime context.

**Expected Result**:
Claude should execute the tool successfully and report a context where:
- `configured_workspace` matches your absolute project path.
- `workspace_detected` is `true`.
- `repo_root` points to your git repository root (if your workspace is a git repo).
- `cwd` might show the process root `/`, but `effective_workspace` successfully points to your configured project.

### Validation Prompt 2: Interactive Approval
> **Prompt**: Using agent-sudo only, run pwd and tell me the current working directory.

**Expected Result**:
1. Claude will attempt to execute `pwd` via `run_shell_command`.
2. The gateway will block the action and report `approval_required`.
3. In your terminal, run the following to inspect the request:
   ```bash
   agent-sudo pending
   ```
4. Approve the request (for example, if it is ID `1`):
   ```bash
   agent-sudo approve 1
   ```
   *(You will be prompted to enter the passphrase configured in step C).*
5. Return to Claude Desktop and ask the agent to retry or continue. The tool execution will succeed and return the output.

---

## H. Common Mistakes

- **Missing `--workspace` value**: Forgetting to add the workspace path argument after the `--workspace` flag.
- **Malformed arguments**: Forgetting to put `--pending-approvals-file` or `--audit-log` in a separate JSON string from their path values.
- **Copy-pasted absolute paths**: Using config files containing placeholder paths or another user's home directories.
- **Inaccessible workspace paths**: Configuring a directory that doesn't exist or is not readable by the user running Claude Desktop.
- **Wrong passphrase**: Typing the wrong passphrase during `agent-sudo approve`.
- **Approval expired**: Waiting longer than the approval TTL (default 120 seconds) to approve a request.
- **Claude using stale processes**: Failing to kill old `agent-sudo-mcp` processes, causing Claude to run older versions of the server code.
- **Runtime starting from `/`**: Failing to configure `--workspace`, resulting in files and commands trying to resolve from the root filesystem.

---

## I. Troubleshooting Commands

Use these terminal commands to diagnose configuration and state issues:

```bash
# Verify CLI and MCP version match
agent-sudo --version
agent-sudo-mcp --version

# Run local sanity checks (checks permissions, scans, config files)
agent-sudo doctor

# Verify context resolution from CLI using your target workspace
agent-sudo context --workspace /path/to/your/project

# Check current pending approvals list
agent-sudo pending
```
