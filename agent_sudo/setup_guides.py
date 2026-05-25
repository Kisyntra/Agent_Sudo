from __future__ import annotations


SETUP_GUIDES = {
    "hermes": [
        "Find the agent runtime config for tool registration.",
        "Remove or restrict direct shell, browser, email, and file-write tools where possible.",
        "Register an agent-sudo wrapper for dangerous tool calls.",
        "Route native tool dictionaries through agent-sudo hermes-check before enabling execution.",
        "Verify with: agent-sudo hermes-check examples/hermes_tool_call.json",
    ],
    "codex": [
        "Configure tool execution through a local wrapper script or SDK boundary.",
        "Do not disable existing safety controls.",
        "Remove direct dangerous tools from the agent profile where possible.",
        "Route native tool dictionaries through agent-sudo codex-check before enabling execution.",
        "Verify with: agent-sudo codex-check examples/codex_tool_call.json",
    ],
    "claude-desktop": [
        "Use a local wrapper around desktop or MCP tools.",
        "Remove direct dangerous tools where the runtime allows it.",
        "Route filesystem, shell, browser, and messaging tools through agent-sudo.",
        "Use the Claude Desktop adapter for native tool-call dictionaries.",
        "Verify with: agent-sudo generic-check examples/claude_desktop_tool_call.json",
    ],
    "openclaw": [
        "Configure the runtime to call an agent-sudo wrapper before tools execute.",
        "Restrict direct browser, shell, and filesystem tools where possible.",
        "Route native tool dictionaries through the OpenClaw adapter.",
        "Use scoped delegations instead of broad approval.",
        "Verify with: agent-sudo generic-check examples/mcp_tool_call.json",
    ],
}


def setup_lines(agent_name: str) -> list[str]:
    return SETUP_GUIDES[agent_name]
