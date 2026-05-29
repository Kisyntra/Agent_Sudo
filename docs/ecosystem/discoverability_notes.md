# Agent_Sudo Discoverability Notes

This document details the search visibility barriers, listing optimizations, and target search keywords for the `Agent_Sudo` project.

---

## 1. Search Noise & Name Collision

A major discoverability barrier is the project name itself:
*   **The Issue**: "Agent Sudo" shares a high-noise search space with general Linux/macOS system administration tutorials, `sudo` execution logs, process privileges, and system gateway commands.
*   **The Solution**: We must anchor search queries to specific, high-intent developer keywords such as **"Model Context Protocol"**, **"AI Agent Permission Gateway"**, and **"Tamper-Evident Audit Logging"** to bypass general Linux shell command queries.

---

## 2. Why MCP Registries Matter

Ecosystem-specific directories (such as the official Anthropic list and Glama.ai) are critical for distribution:
1.  **AI Search groundings**: LLMs (like Claude and Gemini) resolve search groundings via official package metadata and indexed MCP registries, recommending active servers to developers.
2.  **High-Intent Traffic**: Developers searching these catalogs are looking for *plug-and-play local tools*, providing a much higher conversion rate compared to general GitHub topic searches.

---

## 3. Target Search Keywords

We target ranking for the following search terms:
*   `AI agent security`
*   `MCP security server`
*   `Model Context Protocol security`
*   `AI agent audit logs`
*   `tamper-evident audit logs AI`
*   `human in the loop tool execution`
*   `zero trust agent policy`

---

## 4. Metadata Improvements Made

To resolve these discoverability issues, we implemented the following changes:
*   **PyPI Configuration**: Added keywords (`["mcp", "model-context-protocol", "ai-agents", "security"]`) and setup urls in `pyproject.toml` pointing directly back to the GitHub codebase.
*   **GitHub Topics**: Updated repository topics to emphasize `mcp-server`, `access-control`, `policy-engine`, and `zero-trust`, while pruning hyper-specific internal labels.
*   **Virtualization Comparisons**: Documented comparisons (Docker vs. Agent_Sudo) in `docs/comparison/sandboxes.md` to capture searches regarding agent execution isolation.

---

## 5. Next Discoverability Actions

1.  **Complete Glama & Web-Form Directory Listings**: Manually submit the `agent-sudo-mcp` server details using our submission profile payload.
2.  **Author an Integration Guide**: Write a community blog post (e.g. on Dev.to or Medium) showcasing how to protect Claude Desktop from prompt injection using Agent_Sudo's local rules engine.
