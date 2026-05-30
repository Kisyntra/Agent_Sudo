# Hermes Architecture Review

This document preserves research findings regarding the `NousResearch/hermes-agent` tool execution pipeline, extension systems, and security/approval developments, evaluating integration paths for `Agent_Sudo`.

---

## 1. Current Hermes Tool Dispatch Model

Hermes executes tools via `invoke_tool()` in `agent/agent_runtime_helpers.py`. The dispatch model consists of:
* **Inline Special Tools:** A small subset of core tools (`todo`, `memory`, `session_search`, `clarify`) are handled directly within the loop/helpers to access agent-level state. They bypass the registry dispatch entirely.
* **Registry-Dispatched Tools:** All other built-in, plugin-defined, and MCP-served tools are routed to `handle_function_call()` in `model_tools.py` and dispatched via `ToolRegistry.dispatch()`.
* **Subagent Delegation:** Subagents are spawned via `delegate_task`, which executes through `AIAgent._dispatch_delegate_task()` in `run_agent.py` to maintain parent-child thread relationships.

---

## 2. Progressive Tool Disclosure (Tool Search)

Introduced in commit `369075dc9`, the **Tool Search** feature implements progressive disclosure for non-core tools:
* **Trigger:** When the size of registered tool definitions exceeds a configurable context window threshold (default `10%`), all non-core tools are excluded from the model-visible tools array.
* **Bridges:** They are replaced by three bridge tools: `tool_search`, `tool_describe`, and `tool_call`.
* **Execution:** The model searches the catalog dynamically, reads the specific schema, and executes via `tool_call`. In the sequential and concurrent execution paths of `tool_executor.py`, the `tool_call` arguments are unwrapped to the underlying tool name before hooks or guardrails run.

---

## 3. Toolset Scoping

Introduced in commit `7427b9d58`, **Toolset Scoping** allows sessions (such as subagents, kanban workers, or gateway interfaces) to run with a restricted subset of tools:
* **Configuration:** Scopes are defined via `enabled_toolsets` and `disabled_toolsets` keys.
* **Enforcement:** Validation checks are injected in `handle_function_call()` and `tool_executor.py`. Attempting to invoke an out-of-scope tool via `tool_call` or directly returns a scope-violation error immediately, preventing unauthorized tools from executing.

---

## 4. Approval and Security Hardening Developments

Upstream Hermes is actively hardening its security posture across several surfaces:
* **Approval Context Propagation:** Commits `108397726` and `4bdae3477` ensure approval contexts are propagated into parallel python code execution threads, closing a bypass vector where threaded execution skipped manual gating.
* **Platform Security:** Implements fail-closed verification for gateway chat platforms (e.g., Matrix reaction auth checks in `784d8dd2c`).
* **Approved-List Lockdown:** Commit `4f4e337c4` denies write operations to the `pairing/` directories, preventing agents or external inputs from injection-spoofing client authorizations.
* **Security Guidance Plugin:** Commit `249534e47` introduces `security-guidance`, an opt-in plugin scanning tool inputs and results for 25 dangerous coding patterns, providing self-correction feedback or hard-blocking execution if `SECURITY_GUIDANCE_BLOCK=1` is enabled.

---

## 5. Open Hermes Issues

The following open issues highlight active community and maintainer interest in governance and security:

* **Approvals:**
  * **`#34320`:** *Feature: Deterministic approval gate — intercept consequential tool calls before execution*. Proposes a hard code-layer blocker inside `handle_function_call()` rather than prompt-layer guardrails.
  * **`#33905`:** *[Feature]: Per-Tool / Per-Toolset Approval Policies*. Suggests configuring per-tool policies (`always_ask`, `smart`, `deny`) and platform-level overrides.
  * **`#32906`:** *Proposal: per-board approval policy override*.
* **Permissions:**
  * **`#21849`:** *feat: Tool Permission Gating System*. A proposal for a rules-first architecture (`allow`/`deny`/`ask` rules with regex/glob support on commands and paths).
  * **`#21574`:** *RFC: Per-user agent isolation and identity-based permission system*.
  * **`#31988`:** *Skill ownership and permission system for multi-user gateway*.
* **Audit Logs & Governance:**
  * **`#32507`:** *Skill proposal: auditable decision trail for long autonomous coding runs*.
  * **`#26742`:** *First-Class Claim Verification & Audit Mechanism*.

---

## 6. How Agent_Sudo Could Complement Hermes

Agent_Sudo is designed to act as a lightweight, pluggable compliance engine:
* **Separation of Concerns:** Hermes owns execution runtimes, platform messaging APIs (Telegram/Discord), and UI-native approval cards. Agent_Sudo owns the policy parser, authorization evaluation, and cryptographic hash-chain audit logging.
* **Compatibility:** Agent_Sudo can ingest Hermes action requests, return structured `ALLOW`/`DENY`/`REQUIRE_APPROVAL` decisions, and output tamper-evident verification trails, enabling independent verification of Hermes runs.

---

## 7. Why ToolRegistry.dispatch() is Not an Upstream Security Chokepoint

Although the Phase 1 PoC added gating inside `ToolRegistry.dispatch()`, it is not a unified upstream chokepoint because:
1. **Core Bypasses:** Core tools like `todo`, `memory`, `session_search`, `clarify`, and `delegate_task` bypass `ToolRegistry` completely and are executed inline. Gating only `ToolRegistry.dispatch()` leaves these core capabilities unchecked.
2. **Scattered Validation:** Upstream tool validation (such as toolset scoping) is handled at multiple orchestration sites (e.g., `model_tools.py` and `tool_executor.py`) rather than centralized in the registry itself.

---

## 8. Risks of Monkey-Patching ToolRegistry.dispatch()

While monkey-patching `ToolRegistry.dispatch` from a plugin is a quick way to achieve a zero-core-diff integration, it carries several risks:
* **Bypasses:** Standard inline tools (`todo`, `memory`, `session_search`, `clarify`) bypass the registry entirely, leaving those core functions ungated unless `invoke_tool` is also monkey-patched.
* **Brittleness:** Dynamic patching is highly sensitive to changes in method signatures (e.g., `dispatch(name, args, **kwargs)`) or internal registry class reloads.
* **Race Conditions:** Threaded or dynamic reloading of MCP servers can override or reset the registry singleton, clearing the monkey-patched method references.
* **Security Boundaries:** Monkey-patching runs within the same process. A compromised agent thread executing python code can un-patch or overwrite the bridge variables. It serves as policy filtering, not containerized sandboxing.

---

## 9. Recommended Future Integration Path

We recommend leaving Hermes integration as **research-only** and avoiding local forks or monkey-patched releases until:
1. **Upstream Alignment:** Hermes maintainers engage and align on the open proposal issue ([#34992](https://github.com/NousResearch/hermes-agent/issues/34992)).
2. **Native Blocking Hook/Middleware:** Hermes introduces a native blocking middleware or hook framework (like the proposed deterministic approval gate in [#34320](https://github.com/NousResearch/hermes-agent/issues/34320)) that supports custom verification backends.
3. **Concrete Integration Request:** A clear production integration request emerges from the community.
