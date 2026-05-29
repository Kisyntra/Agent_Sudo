# Agent_Sudo Ecosystem Outreach Playbook

This playbook establishes the engagement protocols, communication etiquette, and lessons learned for introducing `Agent_Sudo` to external agent frameworks, runtimes, and developer communities.

---

## 1. Case Studies: What Worked and What Failed

### A. What Worked: `agent-runtimes` (Merges & Integration)
*   **The Approach**: We engaged directly within their existing plugin development lifecycle, aligning on Pull Request #98 to relocate `agent_sudo` into their plugins directory.
*   **Success Factors**:
    *   **Permissive Licensing**: Assuring maintainers that Agent_Sudo remains available under a liberal license (Apache-2.0).
    *   **In-Process Integration**: Gating actions via standard runtime configuration hooks (`before_tool_execute: [agent_sudo_local]`) instead of proposing core runtime alterations.

### B. What Worked: `LexFlow` (Interoperability & Spec Review)
*   **The Approach**: We mapped Victor's field-level questions into a dedicated `Spec Review: LexFlow Interop` milestone on Agent_Sudo, using issues #9–#14 as the canonical discussion points.
*   **Success Factors**:
    *   **Vertical Slicing**: Aligning on a multi-stage implementation (audit-only log emission first, then rule-based gating, then UI, and finally CLI docs).
    *   **Prefix Conventions**: Agreeing to namespaces (e.g. `lexflow_`) to ensure custom metadata fields do not collide across runtimes.

### C. What Failed: `PydanticAI` (Automation Triage Blocking)
*   **The Approach**: We opened Issue #5730 proposing an integration design using PydanticAI's deferred tools capability.
*   **Failure Analysis**:
    *   **Issue Tracker Misuse**: Submitting a general ecosystem proposal directly to their issue tracker (since Discussions were disabled) triggered repository bot automation, which flagged the thread as promotional.
    *   **No Actionable Changes**: The issue lacked a specific code change or documentation PR, presenting as an abstract "advertising" inquiry.

---

## 2. Engagement Hierarchy

When introducing Agent_Sudo to a new framework, follow this communication hierarchy:

```
                  ┌──────────────────────────────┐
                  │ 1. Local Research Artifact   │
                  │    - Map hooks & architecture│
                  └──────────────┬───────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │ 2. GitHub Discussions / Ideas│
                  │    - Seek design feedback    │
                  └──────────────┬───────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │ 3. Docs / Examples PR        │
                  │    - Submit safe demo files  │
                  └──────────────┬───────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │ 4. Code Integration PR       │
                  │    - Final adapter hooks     │
                  └──────────────────────────────┘
```

1.  **GitHub Discussions (Preferred)**: If Discussions are enabled, always submit proposal threads there under the `Ideas` or `Q&A` category.
2.  **Documentation & Examples PRs**: If Discussions are disabled, **do not file an abstract issue**. Instead, submit a Pull Request adding a self-contained code example (e.g., `examples/pydantic_ai/`) or a guide paragraph under their human-in-the-loop documentation files. Maintainers welcome examples because they don't impact core dependencies.
3.  **Code Integration PRs**: Core codebase hooks should only be submitted after the maintainer has explicitly approved the design pattern in a discussion or documentation PR.

---

## 3. The Artifact-First Principle

**Rule**: No external outreach may be initiated before a local research artifact is created and reviewed.

The local research workflow requires:
1.  **Codebase Audit**: Analyze the target repository’s tool execution loop, tool registration decorators, and breakpoint/interrupt handlers.
2.  **Create Integration Templates**: Author concrete integration scripts inside our `examples/` directory showing in-process decorator or graph wrappers.
3.  **Ecosystem Status Update**: Update [docs/ecosystem/ecosystem_status.md](ecosystem_status.md) to record the target's compatibility and current status.
4.  **Write the Design Note**: Create a `docs/integrations/<runtime>-research.md` document detailing the exact integration pathways, boundaries, and limitations.

---

## 4. Maintainer Etiquette

*   **Complement, Do Not Replace**: Always position Agent_Sudo as a pluggable validation and compliance gateway that *complements* the framework's existing tool runtime. (e.g., "Use LangGraph for stateful interrupts; use Agent_Sudo to evaluate YAML policy rules and sign audit logs").
*   **Clear Licensing Guarantees**: Proactively state that Agent_Sudo is Apache-2.0 licensed to avoid IP or vendor-lockout concerns.
*   **No Aggressive Pitching**: Present Agent_Sudo as a reference implementation of a local gatekeeper, rather than asserting it is the only or official solution.
