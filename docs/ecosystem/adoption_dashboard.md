# Agent_Sudo Ecosystem Adoption Dashboard

This dashboard tracks active ecosystem integrations, community implementations, and registry submissions for the `Agent_Sudo` gateway.

---

## Active Engagements & Integrations

### 1. agent-runtimes (Official Integration)
*   **Current Status**: ✅ **Merged & Supported** (PR #98)
*   **Next Milestone**: Support the unified generic plugins architecture (Issue #99) when it stabilizes.
*   **Owner**: Eric Charles / Sri Ram Prakhya
*   **Last Activity**: May 2026 (Merged local plugin config and docs links updates).
*   **Link**: [agent-runtimes Integration Guide](../integrations/agent-runtimes.md) • [PR #98](https://github.com/datalayer/agent-runtimes/pull/98)

### 2. LexFlow (Active Implementation)
*   **Current Status**: 🔄 **In Active Spec Review** (Emitter and verifier CI implementation underway)
*   **Next Milestone**: Verify LexFlow `v0.4.0-rc13` output logs against Agent_Sudo spec helpers in their CI tests.
*   **Owner**: Victor (VforVitorio) / Sri Ram Prakhya
*   **Last Activity**: May 2026 (Aligned on custom namespacing prefix convention `lexflow_` and coordination split).
*   **Link**: [LexFlow #124](https://github.com/VforVitorio/LexFlow/issues/124) • [Coordination Tracker #14](https://github.com/Kisyntra/Agent_Sudo/issues/14)

### 3. NousResearch/hermes-agent (Design Proposal)
*   **Current Status**: 🧪 **Research / Design Proposal Open**
*   **Next Milestone**: Receive core maintainer feedback on proposed core dispatcher gating (`ToolRegistry.dispatch`).
*   **Owner**: NousResearch Maintainers / Sri Ram Prakhya
*   **Last Activity**: May 2026 (Opened design discussion issue #34992).
*   **Link**: [Hermes Integration Research](docs/integrations/hermes-research.md) • [Hermes Issue #34992](https://github.com/NousResearch/hermes-agent/issues/34992)

### 4. PydanticAI (Design Discussion)
*   **Current Status**: ⚠️ **Awaiting Manual Relocation** (Issue #5730 auto-triaged as promotional/spam)
*   **Next Milestone**: Resubmit the proposal under their official documentation or examples contributions (following code-first / example PR patterns).
*   **Owner**: PydanticAI Maintainers / Sri Ram Prakhya
*   **Last Activity**: May 2026 (Opened issue #5730; learned repository bot filters).
*   **Link**: [Outreach Playbook](outreach_playbook.md) • [PydanticAI Issue #5730](https://github.com/pydantic/pydantic-ai/issues/5730)

---

## Registry Listings & Submissions

| Directory / Catalog | Target URL | Submission Method | Status | Links / Reference |
| :--- | :--- | :--- | :--- | :--- |
| **awesome-mcp-servers** | `punkpeye/awesome-mcp-servers` | Pull Request (Draft) | 🔄 **Submitted (Draft PR)** | [PR #7111](https://github.com/punkpeye/awesome-mcp-servers/pull/7111) |
| **Official MCP Registry** | `registry.modelcontextprotocol.io` | `mcp-publisher` CLI | 📋 **Staged** | - |
| **Glama MCP Registry** | `glama.ai/mcp/servers` | OAuth/Manual Form | 📋 **Pending (Manual)** | - |
| **mcpservers.org** | `mcpservers.org` | Web Form Submission | 📋 **Pending (Manual)** | - |
| **modelcontextprotocol/servers** | `modelcontextprotocol/servers` | Pull Request | ❌ **Dropped** (Decision: 2026-05-29) | See Dropped Opportunities |

---

## Registry & Adoption Priority Tiers

To maximize ecosystem impact, our distribution work is structured into the following sequential priority tiers:

### Tier 1: LexFlow Verifier CI Pass
*   **Goal**: Validate independent JS/TS verifier compatibility against the core gateway specifications.
*   **Completion Criteria**: Emitters in the LexFlow codebase successfully compile logs, execute the `agent-sudo verify-audit` command inside their GitHub Actions/CI script, and pass with exit code `0`.

### Tier 2: Glama Activation
*   **Goal**: Manually register the `Agent_Sudo` MCP server on Glama.
*   **Completion Criteria**: The repository is submitted via Glama OAuth, listed publicly at `glama.ai/mcp/servers/Kisyntra/Agent_Sudo`, and shows 100% successful introspection tests on the server capabilities.

### Tier 3: Official MCP Registry Publication
*   **Goal**: Publish server metadata to the official metaregistry using `mcp-publisher`.
*   **Completion Criteria**: The server is queryable via the metaregistry API (`registry.modelcontextprotocol.io/v0/servers?search=agent-sudo-mcp`) and lists correct NPM/PyPI/GitHub package installation directives.

### Tier 4: awesome-mcp Merge
*   **Goal**: Promote and merge the draft pull request on `awesome-mcp-servers`.
*   **Completion Criteria**: The Glama score badge resolves correctly on the PR, CI checks pass, and maintainers merge [PR #7111](https://github.com/punkpeye/awesome-mcp-servers/pull/7111).

### Tier 5: First External User Adoption
*   **Goal**: Verify first real-world developer integration of `Agent_Sudo` tools.
*   **Completion Criteria**: A non-maintainer project implements the permission gateway or consumes the audit log verification libraries in a production AI agent pipeline.

---

## Dropped Opportunities

This section records ecosystem paths that were evaluated and intentionally excluded from current sprints.

### 1. `modelcontextprotocol/servers` Code Submission
*   **Decision Date**: 2026-05-29
*   **Reason for Removal**: The repository is designed and maintained by the MCP steering group solely for hosting core reference implementations and educational samples (SQLite, Filesystem, Google Maps). It does **not** accept community-written servers. Code PRs would be summarily rejected by maintainers, causing unnecessary review friction.
*   **Future Reconsideration Criteria**: We will only reconsider if the MCP steering group changes its policy to allow hosting community-contributed packages, or if `Agent_Sudo` is officially adopted by the steering group as a reference security implementation.
