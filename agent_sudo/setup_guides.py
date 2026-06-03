from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

MCP_EXECUTABLE = "agent-sudo-mcp"
WORKSPACE_PLACEHOLDER = "/ABS/PATH/TO/your/project"


def _mcp_state_paths() -> tuple[str, str, str]:
    """Absolute audit-log, pending-approvals, and delegations paths.

    MCP clients spawn the server with an unpredictable working directory (GUI
    clients often use ``/``), so the server's *relative* audit default
    (``.agent-sudo/mcp-audit.jsonl``) would land somewhere the user cannot find
    and ``agent-sudo audit list`` would not read. The delegations file has no
    server default at all (the store is otherwise ``None`` and tokens are
    ignored), so it must be passed explicitly. Pinning absolute paths keeps the
    server's write locations aligned with the CLI's read/verify locations.
    """
    base = Path.home() / ".agent-sudo"
    return (
        str(base / "mcp-audit.jsonl"),
        str(base / "pending_approvals.json"),
        str(base / "delegations.json"),
    )


def _macos_approval_flags() -> list[str]:
    """Interactive-approval flags that are macOS-only no-ops elsewhere.

    ``--notify`` and ``--open-approval-terminal`` early-return on non-darwin
    platforms, so they are only emitted where they actually do something.
    """
    if sys.platform == "darwin":
        return ["--notify", "--open-approval-terminal"]
    return []


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
    "openclaw": [
        "Configure the runtime to call an agent-sudo wrapper before tools execute.",
        "Restrict direct browser, shell, and filesystem tools where possible.",
        "Route native tool dictionaries through the OpenClaw adapter.",
        "Use scoped delegations instead of broad approval.",
        "Verify with: agent-sudo generic-check examples/mcp_tool_call.json",
    ],
}

# Runtimes that connect over MCP get concrete, pasteable config instead of a
# prose checklist. All are rendered with the resolved agent-sudo-mcp path.
MCP_SETUP_TARGETS = ("codex", "claude-code", "claude-desktop")

SETUP_TARGETS = (*SETUP_GUIDES.keys(), *MCP_SETUP_TARGETS)


def _server_args() -> list[str]:
    """The recommended agent-sudo-mcp args, shared by every MCP client.

    Includes ``--delegations-file`` so the server actually loads a delegation
    store — without it the store is ``None`` and ``agent-sudo delegate create``
    tokens are silently ignored.
    """
    audit_log, pending, delegations = _mcp_state_paths()
    return [
        "--audit-log",
        audit_log,
        "--pending-approvals-file",
        pending,
        "--delegations-file",
        delegations,
        "--workspace",
        WORKSPACE_PLACEHOLDER,
        *_macos_approval_flags(),
    ]


def _rationale_lines() -> list[str]:
    lines = [
        "Absolute --audit-log / --delegations-file / --pending-approvals-file",
        "paths are used on purpose: the MCP client may launch the server from any",
        "directory. Relative paths would hide the audit log, and without",
        "--delegations-file the server runs with no delegation store, so",
        "`agent-sudo delegate create` tokens are silently ignored.",
    ]
    if _macos_approval_flags():
        lines += [
            "--notify and --open-approval-terminal give you an interactive macOS",
            "approval prompt for sensitive/critical actions.",
        ]
    return lines


def _codex_setup() -> list[str]:
    command = resolve_mcp_command()
    audit_log, _, _ = _mcp_state_paths()
    args_toml = ", ".join(f'"{value}"' for value in _server_args())
    return [
        "Codex CLI runs MCP servers defined in ~/.codex/config.toml.",
        "Add this block (create the file if it does not exist):",
        "",
        "[mcp_servers.agent-sudo]",
        f'command = "{command}"',
        f"args = [{args_toml}]",
        "",
        f"Replace {WORKSPACE_PLACEHOLDER} with the absolute path to the project",
        "you want Codex to operate in. Restart Codex CLI after editing the file.",
        "",
        *_rationale_lines(),
        "",
        "Verify with:",
        "  - In a Codex session, confirm the agent-sudo tools (read_file,",
        "    write_file, run_shell_command) are available.",
        f"  - Run a tool, then: agent-sudo audit list {audit_log}",
        "    The call should appear; if it does not, it bypassed agent-sudo.",
    ]


def _claude_code_setup() -> list[str]:
    command = resolve_mcp_command()
    audit_log, _, _ = _mcp_state_paths()
    server_args = " ".join(_server_args())
    return [
        "Claude Code manages MCP servers with the `claude mcp` command.",
        "Add Agent_Sudo (everything after -- is the server command and its args):",
        "",
        f"  claude mcp add agent-sudo -- {command} {server_args}",
        "",
        f"Replace {WORKSPACE_PLACEHOLDER} with the absolute path to your project.",
        "",
        *_rationale_lines(),
        "",
        "Verify with:",
        "  claude mcp list              (agent-sudo should be listed)",
        "  claude mcp get agent-sudo",
        f"  agent-sudo audit list {audit_log}",
        "                               (after a tool call, confirms routing)",
        "",
        "Remove with:",
        "  claude mcp remove agent-sudo",
    ]


def _claude_desktop_setup() -> list[str]:
    command = resolve_mcp_command()
    audit_log, _, _ = _mcp_state_paths()
    config = {
        "mcpServers": {
            "agent-sudo": {
                "command": command,
                "args": _server_args(),
            }
        }
    }
    return [
        "Claude Desktop reads MCP servers from its config file:",
        "  macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json",
        "  Windows: %APPDATA%\\Claude\\claude_desktop_config.json",
        "Merge this into the mcpServers object (create the file if needed):",
        "",
        *json.dumps(config, indent=2).splitlines(),
        "",
        f"Replace {WORKSPACE_PLACEHOLDER} with the absolute path to your project,",
        "then restart Claude Desktop. Each flag and its value is a separate string",
        "in the args array.",
        "",
        *_rationale_lines(),
        "",
        "Verify with:",
        "  - Ask Claude Desktop to use an agent-sudo tool.",
        f"  - Then: agent-sudo audit list {audit_log}",
        "    The call should appear; if it does not, it bypassed agent-sudo.",
    ]


_MCP_SETUP_BUILDERS = {
    "codex": _codex_setup,
    "claude-code": _claude_code_setup,
    "claude-desktop": _claude_desktop_setup,
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
