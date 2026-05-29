# Agent_Sudo

<p align="center">
  <img src="assets/brand/agent-sudo-logo-readme.png" alt="Agent_Sudo logo" width="320">
</p>

## Demo

![Agent_Sudo Demo](assets/demo/demo-agent_sudo.gif)

`Agent_Sudo` is a local permission gateway for AI agents that validates, authorizes, and controls tool execution before actions are run.

---

## Why Agent_Sudo?

> [!IMPORTANT]
> **Security Boundaries Notice**:
> - **Gateway, Not a Sandbox**: `Agent_Sudo` is a local permission gateway and policy engine; it is **not** an OS-level sandbox or container. It gates tool access but does not isolate filesystem or process resources.
> - **Best-Effort Shell Filtering**: Shell command policy checks are best-effort unless reinforced by OS-level containment or custom runtime sandboxes.
> - **Client Runtime Bypass**: Native tools registered directly in host runtimes (e.g., Eino, Hermes) can bypass `Agent_Sudo` entirely unless those tools are disabled or explicitly routed through this gateway.

AI agents can execute powerful local commands and read private files, but they cannot always distinguish authentic user intent from malicious prompt injection, untrusted external content, or over-broad tool permissions.

`Agent_Sudo` intercepts tool calls at execution time, applying least-privilege policies, prompt injection detection, and user-in-the-loop approvals before allowing any tool to run. It acts as an enforcement layer, reducing the blast radius of autonomous agent behavior.

### How is Agent_Sudo different from built-in approvals?

Many agent environments (like Claude Desktop or Cursor) offer static confirmation toggles. Here is how `Agent_Sudo` differs:

| Feature | Built-in Client Approvals | Agent_Sudo Gateway |
| :--- | :--- | :--- |
| **Granularity** | All-or-nothing (e.g., prompt for every tool call) | Fine-grained (allow safe actions, prompt on sensitive, block critical/private directories) |
| **Policy Engine** | Static / hardcoded configurations | Dynamic, user-defined YAML files |
| **Context Aware** | Ignores payload contents | Classifies risk dynamically (e.g., blocks writes to system configurations) |
| **Trust Evaluation** | Treats all requests identically | Tracks request origin (e.g., user-direct vs external-content provenance) |
| **Audit Trails** | Local stdout logs only | Cryptographically secured log files using SHA-256 hash chains |
| **Automation** | Always blocks non-interactive runs | Support for temporary scoped delegation tokens |

---

## Core Features

- **Approval Gates**: Prompts for interactive confirmation (CLI yes/no) on sensitive actions, and requires a local passphrase for critical actions (e.g., running shell commands).
- **Protected Reads**: Automatically blocks reads targeting private files such as credentials, configuration folders, and shell startup scripts.
- **Critical Write Detection**: Upgrades ordinary file writes to critical status if the target is executable code or configuration files.
- **Scoped Delegation**: Allows humans to issue temporary, resource-limited permission tokens (e.g., allow read access to `/path/to/project` for 2 hours, max 10 uses).
- **Audit Logs**: Records all tool attempts and gateway decisions to a local JSONL log file secured with a SHA-256 hash chain to detect log tampering.
- **Claude Desktop / MCP Support**: Implements the Model Context Protocol (MCP) to plug directly into Claude Desktop as a stdio server.

---

## Try it in 30 Seconds

Verify how `Agent_Sudo` classifies tool risk and makes gateway decisions without configuring any agent runtime:

```bash
# Run a dry-run check against a sample tool request
agent-sudo generic-check examples/generic_tool_call.json
```

**Expected Output:**
```json
{"action": "unknown_tool_call", "actor": "agent-a", "approval_attempts": [], "approval_method": "dry_run", "classification": "SENSITIVE", "decision": "REQUIRE_APPROVAL", "dry_run": true, "reason": "SENSITIVE actions require CLI approval; approval skipped in dry-run", "target": "/home/user/example/project"}
```

---

## 5-Minute Quickstart

### 1. Install Agent_Sudo
Install the package from your local clone or repository path:

```bash
pip install agent-sudo
```
*(If you are developing or running from source, see the [Claude Desktop Setup Guide](docs/integrations/claude_desktop_setup.md) for editable installation).*

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

## Contributor Setup

If you are developing `Agent_Sudo` or integrating it with a custom runtime:

```bash
# Clone the repository
git clone https://github.com/Ram9199/Agent_Sudo.git
cd Agent_Sudo

# Install in editable mode
python3 -m pip install -e .
```

To run unit tests:
```bash
python3 -m unittest discover -s tests
```

---

## Documentation Directory

| Directory / Section | Topic | Key Files |
| :--- | :--- | :--- |
| **First Run** | Getting started tutorial | [docs/first_run.md](docs/first_run.md) |
| **Troubleshooting** | Diagnostics and resolution steps | [docs/troubleshooting.md](docs/troubleshooting.md) |
| **Integrations** | Connecting to runtimes and IDEs | [docs/integrations/overview.md](docs/integrations/overview.md) • [Claude Desktop](docs/integrations/claude_desktop_setup.md) • [MCP Setup](docs/integrations/mcp_server_setup.md) |
| **Architecture** | Abstractions and core pipelines | [docs/architecture/overview.md](docs/architecture/overview.md) • [Layered Architecture](docs/architecture/layered_architecture.md) • [Enforcement Model](docs/architecture/enforcement_model.md) |
| **Specifications** | Language-agnostic standard models | [spec/runtime_compatibility_levels.md](spec/runtime_compatibility_levels.md) • [Universal Schema](spec/universal_schema.md) • [Policy & Audit](spec/policy_audit_schema.md) |
| **Security** | Threat modeling and limits | [docs/architecture/security_model.md](docs/architecture/security_model.md) |

---

## CI/CD & Release Automation

`Agent_Sudo` uses GitHub Actions to automate checks and distribution:
- **Continuous Integration**: The CI workflow runs on all pushes and pull requests targeting the `main` branch, running the unittest suite, scanning for personal path disclosures, executing `git diff --check` whitespace validation, and verifying Python package compilation.
- **Automated Releases**: Releases are generated automatically when a git tag matching `v*` is pushed.
  - Release candidate tags (e.g. `v0.4.0-rc12`) are published as GitHub Prereleases and are explicitly excluded from being marked as the latest release.
  - Release notes are automatically parsed and extracted from the matching version entry in `CHANGELOG.md`.
