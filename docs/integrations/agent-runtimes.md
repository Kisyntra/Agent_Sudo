# agent-runtimes Plugin Integration Guide

This guide details how to integrate and use the `Agent_Sudo` plugin within the `agent-runtimes` environment.

---

## 1. Overview

The `Agent_Sudo` plugin integration allows `agent-runtimes` developers to leverage local policy evaluation, user-in-the-loop approvals, and secure audit verification directly within their agent tool execution pipelines.

* **Compatibility Level**: **Level 2 (In-Process Hook Capability)**.
* **Release Status**: Standardized starting with `agent-sudo>=0.4.0rc14` and `agent-runtimes` PR #98.

---

## 2. Installation

`agent-sudo` is registered as an optional dependency in the `agent-runtimes` package. To enable in-process local policy checks, install the runtime with the matching plugin package extra:

```bash
pip install agent-runtimes[agent-sudo]
```

---

## 3. Configuration Examples

### A. Local Plugin Configuration

Register the built-in `agent_sudo_local` plugin hook handler inside your runtime's `tool_hooks` configuration:

```yaml
tool_hooks:
    # Path configuration for local policy rules
    agent_sudo_policy_path: "/path/to/agent_sudo_policy.yaml"
    
    # Target audit log file
    agent_sudo_audit_log_path: "/tmp/agent_runtimes_tool_approvals_audit.jsonl"
    
    # Intercept tool calls prior to execution
    before_tool_execute:
        - handler: agent_sudo_local
```

### B. Audit Verification

Any hooks or plugins outputting Agent_Sudo-compatible records write to the configured audit log path using a cryptographic SHA-256 hash chain to ensure tamper detection. 

To verify the integrity of the emitted logs:

```bash
agent-sudo verify-audit /tmp/agent_runtimes_tool_approvals_audit.jsonl
```

---

## 4. Ownership Boundaries

To keep responsibility separated clearly between the runtime ecosystem and the security gateway:

| Responsibility Area | `agent-runtimes` | `Agent_Sudo` |
| :--- | :---: | :---: |
| **Runtime & Thread Lifecycle** | Control | |
| **Tool Execution & Execution Context** | Control | |
| **Approval UI / WebSocket UX** | Control | |
| **Audit Log File Persistence** | Control | |
| **Policy Evaluation & Rules** | | Control |
| **Passphrase Approvals & Delegation** | | Control |
| **Audit Logs Specifications** | | Control |
| **Verification Tooling (`verify-audit`)** | | Control |

---

## 5. Limitations

* **No OS Isolation**: `Agent_Sudo` is a local permission gateway and policy engine; it is **not** an OS-level sandbox. It checks permissions but does not isolate filesystem paths or sub-process resources.
* **Execution Bypass**: Host runtimes still control actual execution. Any hooks registered outside of `before_tool_execute` (or bypass functions) are not gated by default unless specifically routed.
* **Subject to Change**: The integration is compatible with the current runtime hooks model, but may undergo structural updates when the unified generic plugins architecture (Issue #99) is implemented.

---

## 6. References

* **Pull Request #98**: [agent-runtimes PR #98](https://github.com/datalayer/agent-runtimes/pull/98) — Relocate agent_sudo to plugins directory and implement dynamic registration.
* **Pull Request #97**: [agent-runtimes PR #97](https://github.com/datalayer/agent-runtimes/pull/97) — Document Agent_Sudo-compatible audit logs.
* **GitHub Issue #99**: [agent-runtimes Issue #99](https://github.com/datalayer/agent-runtimes/issues/99) — Design and implement a generic Plugins Architecture.
