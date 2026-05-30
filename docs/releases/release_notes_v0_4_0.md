# Release Notes: Agent_Sudo v0.4.0 (Stable)

We are pleased to announce the first stable public release of the `agent-sudo` local permission gateway and Model Context Protocol (MCP) server: **v0.4.0**.

This release consolidates all previous development and security hardening iterations (rc1 through rc14) into a production-ready permission gating and cryptographic audit logging system for AI agent tool execution.

---

## 🚀 Key Features

### 1. Robust Security Boundaries & Injection Gating
*   **Shell Command Deep-Scanning**: Implements recursive substring and argument scans to detect and block directory traversals (e.g. `../`), environment variable expansion bypasses (such as `$HOME`), symlinks targeting configuration paths, nested subshell escapes (`bash -c`), and copy/pipe utility abuse (`mv`, `cp`, `ln`, `tar`, `tee`, `dd`, `cat`).
*   **Protected Path Redaction**: Restricts access to sensitive config folders (`~/.ssh/`, `~/.config/`, `~/.agent-sudo/`, `~/.agent-runtime/`) and security credentials (`.env`, `auth.json`, `policy.yaml`) for both read and write operations.
*   **Prompt-Injection Defense**: Built-in phrase-based detector flags obvious injection patterns in target inputs prior to gateway execution.

### 2. Tamper-Resistant Cryptographic Auditing
*   **SHA-256 Hash-Chaining**: Generates a tamper-evident cryptographic chain linking every tool call result.
*   **Verification Utility**: Includes the `agent-sudo verify-audit <path/to/audit.jsonl>` CLI utility to programmatically assert the integrity of audit logs.
*   **Interoperability Specification**: Exposes lightweight spec helper APIs and a detailed `Interoperability Test Kit` allowing third-party client implementations (such as LexFlow) to output compatible log files.

### 3. User-in-the-Loop & Temporary Delegation
*   **Pending Approval UX**: Headless MCP environments (like Claude Desktop or Cursor) register pending tool requests. Operators confirm or deny requests from their native terminal with standard `agent-sudo pending / approve / deny` commands.
*   **AppleScript Terminal Opener**: Automatically triggers a macOS Terminal window running the interactive `approval-helper` when a request requires confirmation.
*   **Desktop Notifications**: Standard notifications alert the developer when a tool is blocked awaiting approval.
*   **Scoped Delegation Tokens**: Humans can grant temporary, TTL-limited, and quota-restricted tokens to allow automatic execution of specific tools for specific paths (e.g. allow `write_file` inside `/tmp/project` for 1 hour, max 3 uses).

### 4. Zero-Dependency Packaged Library
*   **No Third-Party Footprint**: Runs strictly on Python 3.10+ standard library features, preventing dependency version conflicts and securing the package against supply-chain vectors.
*   **Standard MCP Support**: Implements standard stdio Model Context Protocol schemas for out-of-the-box integration.

---

## 📦 Build Artifacts
*   **Source Distribution**: `dist/agent_sudo_mcp-0.4.0.tar.gz` (size: 85,689 bytes / ~85.7 KB)
*   **Python Wheel**: `dist/agent_sudo_mcp-0.4.0-py3-none-any.whl` (size: 62,664 bytes / ~62.7 KB)
