# Agent_Sudo Ecosystem Status

This document tracks the integration progress, compatibility levels, and strategic alignment for running the `Agent_Sudo` authorization, delegation, provenance, and verifiable-audit engine across major AI agent frameworks and runtimes.

---

## Ecosystem Mapping & Compatibility

`Agent_Sudo` is designed to be framework-agnostic. Runtimes interface with it at different **Compatibility Levels**:
*   **Level 0 (Stdin/Stdout)**: Low-level command line pipes (e.g. CLI wrapping).
*   **Level 1 (MCP Stdio)**: Standard stdio server communication (e.g., Claude Desktop).
*   **Level 2 (In-Process Hook)**: Rich in-process Python interceptors/decorators.

| Framework / Runtime | GitHub Stars | Sudo Compatibility | Current Integration Status | Primary Integration Pattern |
| :--- | :---: | :---: | :--- | :--- |
| **agent-runtimes** | ~33,000 | Level 2 (Python) | ✅ **Merged & Supported** (PR #98) | Plugin hook (`before_tool_execute`) |
| **LexFlow** | (N/A) | Level 2 (JS/TS) | 🔄 **In Active Spec Review** (#124) | Native JS/TS Audit & Policy Emitter |
| **NousResearch/hermes-agent** | ~171,400+ | Level 2 (Python) | 🧪 **Research/Local PoC** (#34992) | Core registry hook (`ToolRegistry.dispatch`) |
| **pydantic/pydantic-ai** | ~17,400 | Level 2 (Python) | 📖 **Developer Example Available** | Tool decorator wrapping |
| **langchain-ai/langgraph** | ~33,300 | Level 2 (Python) | 📖 **Developer Example Available** | Graph state/ToolNode wrapper |
| **openai/openai-agents-python** | ~26,700 | Level 2 (Python) | 📖 **Developer Example Available** | Tool wrap / SDK interceptor |
| **cloudwego/eino** | ~11,500 | Level 0 & 1 (Go) | 📋 **Proposed** | External Stdio MCP Server |

---

## Integration Guides & Key Patterns

### 1. Unified Plugin (e.g., `agent-runtimes`)
For platforms that feature built-in plugin architectures, `Agent_Sudo` registers as a dynamic tool hook.
*   **Documented in**: [agent-runtimes Integration Guide](../integrations/agent-runtimes.md)
*   **Ownership boundary**: The host runtime manages thread execution and user interfaces, delegating policy evaluation and cryptographic audit signing to `Agent_Sudo`.

### 2. In-Process Decorators (e.g., `PydanticAI` / `OpenAI Agents`)
For code-first SDKs, developers can wrap individual tool functions with standard Python decorators.
*   **Example location**: `examples/pydantic_ai/` • `examples/openai_agents_sdk/`
*   **How it works**: Before the framework executes a tool function, the decorator inspects the call arguments, builds an `ActionRequest`, checks it against the `PermissionGateway`, and raises an exception if denied.

### 3. Graph Nodes / Interceptors (e.g., `LangGraph`)
For graph-based state engines, validation happens either at the edge boundaries or by wrapping standard node runners.
*   **Example location**: [docs/examples/langgraph.md](../examples/langgraph.md) • [examples/langgraph_integration.py](../../examples/langgraph_integration.py)
*   **How it works**: Tool nodes are wrapped in a safe decorator layer that evaluates policy rules, raises dynamic interrupts to halt the graph during pending approvals, and commits verified transactions to the cryptographic audit chain.

---

## Audit Logs & Verifier Tooling

Regardless of the framework used, any integration writing to `Agent_Sudo`-compatible audit logs outputs a cryptographic SHA-256 hash chain to detect tampering. Logs can be verified using the standard CLI helper:

```bash
agent-sudo verify-audit /path/to/audit.jsonl
```
