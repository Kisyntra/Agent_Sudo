# Agent_Sudo Ecosystem Outreach Playbook

This playbook establishes the engagement protocols, communication etiquette, and lessons learned for introducing `Agent_Sudo` to external agent frameworks, runtimes, and developer communities.

---

## 1. Outreach Objective

Generate evaluator conversations from existing problem-aware communities rather than broad marketing outreach.

The target reader is already building agents, MCP tooling, approval flows, audit systems, or governance infrastructure. Do not pitch generic AI communities, startup groups, broad product-launch channels, or cold email lists.

The first ask should be narrow:

> I built a local MCP permission gateway that demonstrates blocked -> delegated -> allowed once -> blocked again -> audit verified. Does this match the tool-governance problem you were discussing here?

Every outreach attempt must be tied to a specific source URL and a specific reason the person or thread was selected.

---

## 2. Discovery Source Priorities

### Priority 1: Existing Problem-Aware Users

Start with people who already demonstrated willingness to install, critique, or discuss agent-governance tools.

1.  **Node9 issue tracker participants**
    *   Bug reporters
    *   Feature request authors
    *   Discussion participants
    *   Reason: These users have already demonstrated willingness to install agent-governance tools and provide feedback.
2.  **"sudo for agents" discussions**
    *   Dev.to posts
    *   Blog comments
    *   GitHub Discussions
    *   Reddit discussions
    *   Reason: These users already recognize the problem category.

Selection signals:

*   Mentions of approval gates, allow/deny policy, shell/file permissions, scoped delegation, audit logs, agent tool governance, or prompt-injection blast radius.
*   Evidence that the user installed or evaluated a related project.
*   A live question or unresolved pain that Agent_Sudo's current evaluator path can answer without proposing new features.

### Priority 2: MCP Ecosystem

Then target people already publishing or maintaining MCP tooling.

1.  MCP Registry publishers
2.  MCP server maintainers
3.  Awesome MCP Server contributors
4.  FastMCP ecosystem contributors
5.  MCP Discord participants
6.  `r/mcp` contributors

Reason: Agent_Sudo naturally fits MCP workflows and now has a five-minute evaluator path that does not require understanding the internal architecture.

Selection signals:

*   Maintains a server that exposes shell, filesystem, browser, network, or write-capable tools.
*   Discusses MCP safety, permissions, logging, human review, tool provenance, or deployment hardening.
*   Publishes examples where a local permission gateway could be evaluated as a wrapper or companion.

### Priority 3: PydanticAI Ecosystem

Use the existing PydanticAI example as the concrete artifact.

1.  PydanticAI contributors
2.  Logfire contributors
3.  GitHub discussion participants
4.  Community example authors

Reason: Agent_Sudo already has a working PydanticAI example. The outreach should ask for evaluator feedback on the example and the local governance pattern, not for a core integration commitment.

Selection signals:

*   Human-in-the-loop, deferred tools, tool approval, observability, or evaluation discussions.
*   Community examples that execute tools or modify files.
*   Maintainers asking for concrete examples rather than abstract proposals.

### Priority 4: Governance / Safety Builders

Use this group for high-context validation once the first three priorities are moving.

1.  Agent guardrail projects
2.  Human-in-the-loop projects
3.  Approval workflow projects
4.  Auditability projects

Reason: These builders are likely to understand the problem immediately and can provide compatibility, schema, and positioning feedback.

Selection signals:

*   Existing work on runtime approval, action review, policy decisions, traceability, or tamper-evident logs.
*   Public issues asking how to verify agent behavior or bound tool permissions.
*   Maintainers comparing policy gateways, guardrails, sandboxing, and audit logs.

---

## 3. Channel Priority Order

Use channels in this order:

1.  GitHub Issues
2.  GitHub Discussions
3.  GitHub Profiles
4.  Project Discord communities
5.  Reddit communities
6.  X/Twitter

Preferred channel rules:

*   Use GitHub Issues only when the thread is already about the exact problem and a concrete artifact is relevant.
*   Use GitHub Discussions for design feedback, ecosystem fit, and evaluator asks.
*   Use GitHub Profiles only to find the maintainer's preferred contact or linked community; do not scrape for cold email.
*   Use Discord and Reddit only in relevant project or MCP communities, with the same source-specific context.
*   Use X/Twitter last, only when the source discussion originated there or the maintainer explicitly uses it for project discussion.

Avoid:

*   Cold mass-emailing
*   Generic marketing communities
*   Startup groups
*   Broad AI groups
*   Copy/pasted comments
*   Locked, stale, or mismatched threads

### Effort Allocation

Spend outreach effort roughly as follows until reply data suggests otherwise:

| Channel | Effort | Rationale |
| :--- | :--- | :--- |
| GitHub | 60% | Highest signal for issue-specific, artifact-backed evaluator conversations. |
| Discord | 20% | Useful after identifying project communities where maintainers already discuss MCP or agent tooling. |
| Reddit | 10% | Useful for `r/mcp` and adjacent technical discussions when the thread is already problem-aware. |
| Dev.to | 5% | Useful only for commenters on "sudo for LLMs", "sudo for agents", MCP security, or AI governance posts. |
| X/Twitter | 5% | Last resort for MCP builders, FastMCP builders, PydanticAI contributors, and agent-security discussions already happening there. |

The first ten direct targets should come from Priority 1 and Priority 2 unless a higher-signal live reply appears elsewhere.

---

## 4. Target Record Requirements

Actual target records belong in a local-only ledger such as `outreach_ledger.local.md`, `outreach_ledger.private.md`, or `maintainer/outreach_ledger.md`. The repo-local ignore rules keep these files out of public commits.

Every target record must include:

| Field | Required content |
| :--- | :--- |
| `source_community` | Node9, "sudo for agents" discussion, MCP Registry, Awesome MCP, FastMCP, MCP Discord, `r/mcp`, PydanticAI, Logfire, guardrail project, approval workflow project, etc. |
| `source_url` | Exact issue, discussion, PR, comment, profile, registry page, Reddit thread, Discord permalink, or post URL. |
| `person_or_project` | Maintainer, reporter, commenter, contributor, or project name. |
| `why_selected` | One or two sentences tying the target to existing problem evidence. |
| `priority` | P1, P2, P3, or P4. |
| `outreach_channel_used` | GitHub Issue, GitHub Discussion, GitHub Profile, Discord, Reddit, or X/Twitter. |
| `message_angle` | The thread-specific reason to mention Agent_Sudo. |
| `artifact_shared` | The exact artifact linked, usually `docs/evaluate_5_minutes.md`, the PydanticAI example, audit verifier docs, or an integration guide. |
| `status` | Research-only, queued, sent, replied, follow-up queued, not a fit, skipped. |
| `reply_signal` | Validation, compatibility interest, adoption intent, objection, not relevant, or no reply. |
| `next_action` | The next concrete step, or `none`. |

Template:

```markdown
## Target: <person_or_project>

- source_community:
- source_url:
- why_selected:
- priority:
- outreach_channel_used:
- message_angle:
- artifact_shared:
- status:
- reply_signal:
- next_action:
```

Do not count a positive reply as adoption. Track validation, compatibility interest, and real adoption intent separately.

---

## 5. Engagement Workflow

1.  **Identify**: Search only in the priority communities above. Skip broad AI chatter.
2.  **Qualify**: Confirm the source URL contains explicit evidence of tool-governance pain.
3.  **Match artifact**: Pick one concrete artifact to share:
    *   First-time MCP evaluation: `docs/evaluate_5_minutes.md`
    *   PydanticAI fit: `examples/pydantic_ai/`
    *   Audit/verifier fit: `agent-sudo verify-audit` docs or schema docs
    *   MCP setup fit: `docs/integrations/mcp_server_setup.md`
4.  **Write thread-specific outreach**: Reference the exact issue or discussion. Do not use generic marketing language.
5.  **Record before posting**: Add the target record to the local-only ledger.
6.  **Engage once**: Ask for evaluator feedback or fit validation. Do not push for adoption immediately.
7.  **Track response**: Record replies as validation, compatibility interest, adoption intent, or objection.
8.  **Follow up only with new value**: A demo result, compatibility note, issue answer, or requested artifact.

---

## 6. Message Patterns

### GitHub Issue or Discussion

```text
This looks close to a problem I have been working on: bounding what an agent can do after it requests a risky tool call.

I built Agent_Sudo as a local MCP permission gateway and the current 5-minute evaluation path is intentionally narrow: blocked -> delegated -> allowed once -> blocked again -> audit verified.

Would that evaluation model fit the issue you are describing here, or is your main concern somewhere else in the tool flow?
```

### MCP Maintainer

```text
I noticed this MCP server exposes <tool category>. I am looking for feedback from maintainers who already think about tool boundaries.

Agent_Sudo's evaluator path shows a single critical tool request being blocked, delegated for one use, blocked again after exhaustion, then verified in the audit log.

Is that a useful governance layer for this kind of server, or would it miss the way your users actually run tools?
```

### PydanticAI Example Author or Contributor

```text
I saw your PydanticAI example/discussion around <specific tool or workflow>.

Agent_Sudo has a working PydanticAI example for local approval/delegation/audit behavior. I am trying to validate whether the example matches how PydanticAI users actually wrap risky tools.

Would feedback on that example be welcome?
```

### Governance / Safety Builder

```text
Your project seems focused on <approval/audit/guardrail area>. Agent_Sudo is taking a narrow local-gateway approach: gate tool calls, support scoped delegation, and verify a hash-chained audit log.

The quickest way to evaluate it is the 5-minute blocked -> delegated -> allowed once -> blocked again -> audit verified path.

Does that overlap with your model, or are you solving a different part of the governance problem?
```

---

## 7. Case Studies: What Worked and What Failed

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

## 8. Engagement Hierarchy

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

## 9. The Artifact-First Principle

**Rule**: No external outreach may be initiated before a local research artifact is created and reviewed.

The local research workflow requires:
1.  **Codebase Audit**: Analyze the target repository’s tool execution loop, tool registration decorators, and breakpoint/interrupt handlers.
2.  **Create Integration Templates**: Author concrete integration scripts inside our `examples/` directory showing in-process decorator or graph wrappers.
3.  **Ecosystem Status Update**: Update [docs/ecosystem/ecosystem_status.md](ecosystem_status.md) to record the target's compatibility and current status.
4.  **Write the Design Note**: Create a `docs/integrations/<runtime>-research.md` document detailing the exact integration pathways, boundaries, and limitations.

---

## 10. Maintainer Etiquette

*   **Complement, Do Not Replace**: Always position Agent_Sudo as a pluggable validation and compliance gateway that *complements* the framework's existing tool runtime. (e.g., "Use LangGraph for stateful interrupts; use Agent_Sudo to evaluate YAML policy rules and sign audit logs").
*   **Clear Licensing Guarantees**: Proactively state that Agent_Sudo is Apache-2.0 licensed to avoid IP or vendor-lockout concerns.
*   **No Aggressive Pitching**: Present Agent_Sudo as a reference implementation of a local gatekeeper, rather than asserting it is the only or official solution.
