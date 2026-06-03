from __future__ import annotations

import shutil
import sys
from pathlib import Path

MCP_EXECUTABLE = "agent-sudo-mcp"
WORKSPACE_PLACEHOLDER = "/ABS/PATH/TO/your/project"


def resolve_mcp_command() -> str:
    """Best-effort absolute path to the ``agent-sudo-mcp`` console script.

    Resolution order:

    1. ``agent-sudo-mcp`` on ``PATH`` (covers ``pipx install`` and
       ``pip install``/editable installs that expose the console script).
    2. A sibling of the running interpreter (covers an active virtualenv whose
       ``bin``/``Scripts`` directory is not the first match on ``PATH``).
    3. The bare command name, so the printed config is still correct once
       ``agent-sudo-mcp`` is installed and on ``PATH``.
    """
    found = shutil.which(MCP_EXECUTABLE)
    if found:
        return found
    sibling = Path(sys.executable).resolve().parent / MCP_EXECUTABLE
    if sibling.exists():
        return str(sibling)
    return MCP_EXECUTABLE


# Prose checklists for runtimes that integrate by wrapping native tool calls
# rather than connecting over MCP.
SETUP_GUIDES = {
    "hermes": [
        "Find the agent runtime config for tool registration.",
        "Remove or restrict direct shell, browser, email, and file-write tools where possible.",
        "Register an agent-sudo wrapper for dangerous tool calls.",
        "Route native tool dictionaries through agent-sudo hermes-check before enabling execution.",
        "Verify with: agent-sudo hermes-check examples/hermes_tool_call.json",
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

# Runtimes that connect over MCP get concrete, pasteable config instead of a
# prose checklist. Both are rendered with the resolved agent-sudo-mcp path.
MCP_SETUP_TARGETS = ("codex", "claude-code")

SETUP_TARGETS = (*SETUP_GUIDES.keys(), *MCP_SETUP_TARGETS)


def _codex_setup() -> list[str]:
    command = resolve_mcp_command()
    return [
        "Codex CLI runs MCP servers defined in ~/.codex/config.toml.",
        "Add this block (create the file if it does not exist):",
        "",
        "[mcp_servers.agent-sudo]",
        f'command = "{command}"',
        f'args = ["--workspace", "{WORKSPACE_PLACEHOLDER}"]',
        "",
        f"Replace {WORKSPACE_PLACEHOLDER} with the absolute path to the project",
        "you want Codex to operate in. Restart Codex CLI after editing the file.",
        "",
        "Verify with:",
        "  - In a Codex session, confirm the agent-sudo tools (read_file,",
        "    write_file, run_shell_command) are available.",
        "  - Run a tool, then: agent-sudo audit list   (the call should appear).",
        "    If the call is not listed, it bypassed agent-sudo.",
    ]


def _claude_code_setup() -> list[str]:
    command = resolve_mcp_command()
    return [
        "Claude Code manages MCP servers with the `claude mcp` command.",
        "Add Agent_Sudo (everything after -- is the server command and its args):",
        "",
        f"  claude mcp add agent-sudo -- {command} --workspace {WORKSPACE_PLACEHOLDER}",
        "",
        f"Replace {WORKSPACE_PLACEHOLDER} with the absolute path to your project.",
        "",
        "Verify with:",
        "  claude mcp list              (agent-sudo should be listed)",
        "  claude mcp get agent-sudo",
        "  agent-sudo audit list        (after a tool call, confirms routing)",
        "",
        "Remove with:",
        "  claude mcp remove agent-sudo",
    ]


_MCP_SETUP_BUILDERS = {
    "codex": _codex_setup,
    "claude-code": _claude_code_setup,
}


def setup_lines(agent_name: str) -> list[str]:
    """Return the body lines for a setup target.

    MCP targets return pasteable config; the others return a prose checklist.
    """
    if agent_name in _MCP_SETUP_BUILDERS:
        return _MCP_SETUP_BUILDERS[agent_name]()
    return SETUP_GUIDES[agent_name]


def render_setup(agent_name: str) -> str:
    """Render the full ``agent-sudo setup <target>`` output."""
    header = [
        f"agent-sudo setup for {agent_name}",
        "dry-run only: no config files were edited",
        "",
    ]
    body = setup_lines(agent_name)
    if agent_name not in _MCP_SETUP_BUILDERS:
        body = [f"{index}. {line}" for index, line in enumerate(body, start=1)]
    return "\n".join(header + body)
