# Claude Desktop Setup Guide

This guide explains how to install `Agent_Sudo`, connect it to Claude Desktop as a Model Context Protocol (MCP) server, and validate the setup.

> [!IMPORTANT]
> **What the MCP server is for.** Agent_Sudo is an authorization, approval, delegation, and audit **engine**. Wired into Claude Desktop, it lets you **observe, gate, and audit** the tool calls routed through its server — `read_file` executes for real, and every routed call is classified and logged. The `write_file` and `run_shell_command` tools are **reference/demo executors** (`write_file` writes only inside `/tmp/agent-sudo-demo`; shell runs a narrow allowlist). They demonstrate gating; they do **not** mediate Claude Desktop's own file/shell tools and are not a turnkey way to protect arbitrary writes or commands. To gate **real** tool execution, embed the engine in your agent — see the [README](../../README.md) integration path and [framework examples](../../examples/).

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
pip install agent-sudo-mcp
```

### Developer / Editable Installation
If running from a local checkout or developing changes:
```bash
git clone https://github.com/Kisyntra/Agent_Sudo.git
cd Agent_Sudo
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

First persist the fixed workspace that Claude Desktop should use:

```bash
agent-sudo workspace set /path/to/project
agent-sudo workspace show
```

Claude Desktop reads its MCP server configuration from a local JSON file.

1. Open the configuration file at:
   `~/Library/Application Support/Claude/claude_desktop_config.json`
2. Add `agent-sudo` to the `mcpServers` object. If you ran `agent-sudo workspace set`, the `--workspace` argument can be omitted because the MCP server reads `~/.agent-sudo/config.json` on startup:

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
        "--notify",
        "--open-approval-terminal"
      ]
    }
  }
}
```

> [!IMPORTANT]
> - **Separate arguments**: Each command line flag and its value must be specified as a **separate** JSON string in the `args` array.
> - **Workspace Config**: Run `agent-sudo workspace set /path/to/project` before starting Claude Desktop. `--workspace /path/to/project` is still supported as an explicit override, but the recommended Claude Desktop config can omit it once the persisted workspace is set. Claude Desktop launches MCP servers from the root `/` directory by default, so starting without either persisted workspace config or `--workspace` will cause context detection to fail.
> - **Desktop Notifications**: Enabling `"--notify"` in `args` (or setting the environment variable `AGENT_SUDO_NOTIFY=1` before launching Claude) allows `Agent_Sudo` to trigger a native macOS user notification (using `osascript`) whenever an approval request is generated, warning the operator to run `agent-sudo pending` without having to poll the terminal constantly.
>   - **Optional & Default OFF**: Notifications must be explicitly enabled using the flag or environment variable.
>   - **macOS-only**: This is currently macOS-only MVP behavior.
>   - **Non-blocking & Safe**: If a notification fails to trigger or display, the operation will proceed normally without blocking approval creation or failing the MCP execution.
> - **Auto-Open Guided Terminal**: Enabling `"--open-approval-terminal"` in `args` (or setting the environment variable `AGENT_SUDO_OPEN_APPROVAL_TERMINAL=1`) automatically opens a new macOS Terminal.app window running `agent-sudo approval-helper --auto-opened` when a pending approval request is generated.
>   - **Optional & Default OFF**: This is disabled by default.
>   - **macOS-only**: Spawning a terminal window automatically is currently macOS-only behavior.
>   - **Clean UX & Auto-Close**: The auto-opened terminal clears the screen to suppress login shell warnings/motd noise. It sanitizes path details to filenames, and automatically closes the window exactly 3 seconds after successfully approving or denying a single pending request. If verification fails, multiple requests exist, or config is missing, it stays open and blocks on a `Press Enter to exit...` prompt so you can inspect the output/logs.
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

## F2. Close the Bypass — Make Sure Tools Actually Route Through Agent_Sudo

> [!WARNING]
> **Adding the `agent-sudo` MCP server does not, by itself, protect every action.** Agent_Sudo can only gate, deny, or log the tool calls that are **routed through it**. Claude Desktop's own built-in tools and any *other* MCP servers you have installed (filesystem, shell, web, etc.) can perform file, shell, and network actions **without ever touching Agent_Sudo** — those actions are not gated and will not appear in your audit log.

To rely on Agent_Sudo as a control, you must ensure the agent's risky capabilities flow through it and **not** around it:

1. **Inventory the agent's tools.** In Claude Desktop, review the configured connectors/MCP servers. Anything that exposes filesystem, shell, or network access *other than* `agent-sudo` is a bypass path.
2. **Disable or remove competing tools.** Remove other MCP servers that grant direct file/shell/network access (or restrict them), so the agent must use `agent-sudo` for those operations. If a client built-in tool can perform the action directly, instruct the agent to use `agent-sudo` only (see the validation prompts below), and treat the built-in as out-of-scope/untrusted.
3. **Prefer least privilege.** Only expose the capabilities you actually need through the gateway.

### Verify nothing bypassed the gateway

After exercising the agent, confirm its actions were actually mediated:

```bash
agent-sudo audit list
```

- Every action you expected the agent to take should appear as a row (time, decision, actor, action, target, reason).
- **If an action you asked for is *missing* from the list, it bypassed Agent_Sudo and was not protected.** Find the tool that performed it (a client built-in or another MCP server) and disable/route it.

For a structured summary of the same picture, run:

```bash
agent-sudo verify-routing
```

It reports configuration, observed gateway activity (record count + hash-chain integrity), a best-effort scan of your Claude Desktop config for `agent-sudo` and any *other* MCP servers that could bypass it, and the trust-boundary limits that always apply. It is read-only and deliberately makes no "you are protected" claim — absence of records is not proof of safety. Use it to spot bypass paths and confirm the gateway is receiving requests; use `agent-sudo audit list` to confirm a *specific* action was gated.

> [!IMPORTANT]
> Agent_Sudo is a **policy gateway, not an OS sandbox**. Even when every tool is routed correctly, shell filtering is best-effort. For environment-level isolation, run the agent inside Docker/Firecracker in addition to Agent_Sudo. See [Agent_Sudo vs. Container/VM Sandboxes](../comparison/sandboxes.md).

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

- **Missing workspace config**: Starting Claude Desktop before running `agent-sudo workspace set /path/to/project`, or passing `--workspace` without a path value.
- **Malformed arguments**: Forgetting to put `--pending-approvals-file` or `--audit-log` in a separate JSON string from their path values.
- **Copy-pasted absolute paths**: Using config files containing placeholder paths or another user's home directories.
- **Inaccessible workspace paths**: Configuring a directory that doesn't exist or is not readable by the user running Claude Desktop.
- **Wrong passphrase**: Typing the wrong passphrase during `agent-sudo approve`.
- **Approval expired**: Waiting longer than the approval TTL (default 120 seconds) to approve a request.
- **Claude using stale processes**: Failing to kill old `agent-sudo-mcp` processes, causing Claude to run older versions of the server code.
- **Runtime starting from `/`**: Failing to configure a persisted workspace or `--workspace`, resulting in files and commands trying to resolve from the root filesystem.

---

## I. Troubleshooting Commands

Use these terminal commands to diagnose configuration and state issues:

```bash
# Verify CLI and MCP version match
agent-sudo --version
agent-sudo-mcp --version

# Run local sanity checks (checks permissions, scans, config files)
agent-sudo doctor

# Verify the persisted workspace
agent-sudo workspace show

# Verify runtime context resolution from the persisted workspace
agent-sudo context

# Check current pending approvals list
agent-sudo pending
```
