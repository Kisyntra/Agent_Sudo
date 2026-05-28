# Agent_Sudo

<p align="center">
  <img src="assets/brand/agent-sudo-logo-readme.png" alt="Agent_Sudo logo" width="320">
</p>

`Agent_Sudo` is a local permission gateway for AI agents that validates, authorizes, and controls tool execution before actions are run.

## Why Agent_Sudo?

AI agents can execute powerful local commands and read private files, but they cannot always distinguish authentic user intent from malicious prompt injection, untrusted external content, or over-broad tool permissions.

`Agent_Sudo` intercepts tool calls at execution time, applying least-privilege policies, prompt injection detection, and user-in-the-loop approvals before allowing any tool to run. It acts as an enforcement layer, reducing the blast radius of autonomous agent behavior.

## Core Features

- **Approval Gates**: Prompts for interactive confirmation (CLI yes/no) on sensitive actions, and requires a local passphrase for critical actions (e.g., running shell commands).
- **Protected Reads**: Automatically blocks reads targeting private files such as credentials, configuration folders, and shell startup scripts.
- **Critical Write Detection**: Upgrades ordinary file writes to critical status if the target is executable code or configuration files.
- **Scoped Delegation**: Allows humans to issue temporary, resource-limited permission tokens (e.g., allow read access to `/path/to/project` for 2 hours, max 10 uses).
- **Audit Logs**: Records all tool attempts and gateway decisions to a local JSONL log file secured with a SHA-256 hash chain to detect log tampering.
- **Claude Desktop / MCP Support**: Implements the Model Context Protocol (MCP) to plug directly into Claude Desktop as a stdio server.

---

## 5-Minute Quickstart

### 1. Install Agent_Sudo
Install the package from your local clone or repository path:

```bash
pip install agent-sudo
```
*(If you are developing or running from source, see the [Claude Desktop Setup Guide](docs/CLAUDE_DESKTOP_SETUP.md) for editable installation).*

Verify the installation:
```bash
agent-sudo --version
agent-sudo doctor
```

### 2. Initialize the Approval Passphrase
Set up a secure passphrase for approving critical actions (e.g. shell command execution):

```bash
agent-sudo init-approval
```
> [!IMPORTANT]
> This passphrase is hashed locally (PBKDF2-HMAC-SHA256) and cannot be recovered. If lost, you must reset the approval configuration.

### 3. Check Context
Verify that the runtime context matches your current directory:
```bash
agent-sudo context
```

---

## Documentation Links

- **[Claude Desktop Setup Guide](docs/CLAUDE_DESKTOP_SETUP.md)**: Connect `Agent_Sudo` to Claude Desktop, configure the active workspace, and run verification tests.
- **[Troubleshooting Guide](docs/TROUBLESHOOTING.md)**: Solutions for common startup errors, passphrase failures, and workspace detection issues.
- **[Security & Threat Model](docs/SECURITY_MODEL.md)**: Deep dive into the security boundaries, audit log guarantees, and future hardening plans.
