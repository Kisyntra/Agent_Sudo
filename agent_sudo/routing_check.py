"""Read-only routing/bypass evidence reporter for `agent-sudo verify-routing`.

This module observes local state to help a user judge whether their agent's
actions are flowing *through* Agent_Sudo. It is deliberately observational:

- It never probes the client, executes anything, or emits telemetry.
- It never claims the user "is protected" — Agent_Sudo cannot prove that.
- It reports no aggregate PASS; only per-signal observed facts and the
  structural limitations that always apply.

See docs/reports/bypass_doctor_design.md for the design and rationale.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from agent_sudo.approvals import CONFIG_PATH as APPROVAL_CONFIG_PATH
from agent_sudo.approvals import load_approval_config
from agent_sudo.audit import read_audit_entries, verify_audit_log
from agent_sudo.context import load_agent_sudo_config

# Sections, in display order.
SECTION_CONFIG = "Configuration (what is set up)"
SECTION_ACTIVITY = "Observed gateway activity (what actually reached the gateway — past tense)"
SECTION_WIRING = "MCP client wiring (best-effort — parsed from client config if present)"
SECTION_BOUNDARY = "Trust boundary (cannot be proven from local state)"

# Default macOS Claude Desktop client config. Best-effort; absence is reported
# neutrally, never as a failure (the user may run a client we cannot read).
DEFAULT_CLIENT_CONFIG_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Claude"
    / "claude_desktop_config.json"
)

# Default MCP audit log locations, checked in order.
def _default_audit_paths(repo_root: Path) -> list[Path]:
    return [
        repo_root / ".agent-sudo" / "mcp-audit.jsonl",
        Path.home() / ".agent-sudo" / "mcp-audit.jsonl",
    ]


class Status(str, Enum):
    OBSERVED = "OBSERVED"  # rendered as ✓ — a fact proven from local state
    LIMITATION = "LIMITATION"  # rendered as ⚠ — best-effort or structural limit
    MISCONFIG = "MISCONFIG"  # rendered as ✗ — a provable misconfiguration


_ICON = {Status.OBSERVED: "✓", Status.LIMITATION: "⚠", Status.MISCONFIG: "✗"}


@dataclass(frozen=True)
class Signal:
    section: str
    status: Status
    label: str
    detail: str = ""


def run_routing_check(
    *,
    repo_root: Path | None = None,
    approval_config_path: Path | None = None,
    workspace_config_path: Path | None = None,
    audit_paths: list[Path] | None = None,
    client_config_path: Path | None = None,
) -> list[Signal]:
    """Collect routing-evidence signals from local state. Read-only."""
    root = repo_root or Path.cwd()
    signals: list[Signal] = []
    signals.extend(_configuration_signals(approval_config_path, workspace_config_path))
    signals.extend(
        _activity_signals(audit_paths or _default_audit_paths(root))
    )
    signals.extend(_wiring_signals(client_config_path))
    signals.extend(_boundary_signals())
    return signals


# --- Configuration ---------------------------------------------------------


def _configuration_signals(
    approval_config_path: Path | None, workspace_config_path: Path | None
) -> list[Signal]:
    out: list[Signal] = []
    approval = load_approval_config(approval_config_path or APPROVAL_CONFIG_PATH)
    if approval is not None:
        out.append(
            Signal(
                SECTION_CONFIG,
                Status.OBSERVED,
                "approvals initialized",
                _display_path(approval_config_path or APPROVAL_CONFIG_PATH),
            )
        )
    else:
        out.append(
            Signal(
                SECTION_CONFIG,
                Status.MISCONFIG,
                "approvals not initialized",
                "run: agent-sudo init-approval",
            )
        )

    config = load_agent_sudo_config(workspace_config_path)
    workspace = config.get("workspace")
    if workspace:
        out.append(
            Signal(SECTION_CONFIG, Status.OBSERVED, "workspace configured", str(workspace))
        )
    else:
        out.append(
            Signal(
                SECTION_CONFIG,
                Status.LIMITATION,
                "workspace not configured",
                "run: agent-sudo workspace set /ABS/PATH",
            )
        )
    return out


# --- Observed gateway activity --------------------------------------------


def _activity_signals(audit_paths: list[Path]) -> list[Signal]:
    audit_path = next((p for p in audit_paths if p.exists()), None)
    if audit_path is None:
        return [
            Signal(
                SECTION_ACTIVITY,
                Status.LIMITATION,
                "no audit log found yet",
                "expected at "
                + " or ".join(_display_path(p) for p in audit_paths),
            )
        ]

    out = [
        Signal(
            SECTION_ACTIVITY, Status.OBSERVED, "audit log present", _display_path(audit_path)
        )
    ]

    verified, message = verify_audit_log(audit_path)
    out.append(
        Signal(
            SECTION_ACTIVITY,
            Status.OBSERVED if verified else Status.MISCONFIG,
            "audit integrity verified" if verified else "audit integrity check FAILED",
            message,
        )
    )

    try:
        entries = read_audit_entries(audit_path)
    except (OSError, json.JSONDecodeError) as exc:
        out.append(
            Signal(
                SECTION_ACTIVITY,
                Status.MISCONFIG,
                "audit log unreadable",
                str(exc),
            )
        )
        return out

    if not entries:
        out.append(
            Signal(
                SECTION_ACTIVITY,
                Status.LIMITATION,
                "no requests observed yet",
                "run a tool through your agent, then re-check",
            )
        )
        return out

    histogram = _decision_histogram(entries)
    last_ts = _last_timestamp(entries)
    summary = " · ".join(f"{decision} {count}" for decision, count in histogram)
    out.append(
        Signal(
            SECTION_ACTIVITY,
            Status.OBSERVED,
            "requests observed",
            f"{len(entries)} records; last record at {last_ts}"
            + (f"; decisions: {summary}" if summary else ""),
        )
    )
    return out


def _decision_histogram(entries: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for entry in entries:
        if entry.get("event_type") == "gateway_decision":
            decision = str(entry.get("decision", "UNKNOWN"))
            counts[decision] = counts.get(decision, 0) + 1
    return sorted(counts.items())


def _last_timestamp(entries: list[dict]) -> str:
    for entry in reversed(entries):
        ts = entry.get("timestamp")
        if ts:
            return str(ts)
    return "unknown"


# --- MCP client wiring (best-effort) --------------------------------------


def _wiring_signals(client_config_path: Path | None) -> list[Signal]:
    path = client_config_path or DEFAULT_CLIENT_CONFIG_PATH
    if not path.exists():
        return [
            Signal(
                SECTION_WIRING,
                Status.LIMITATION,
                "client config not found (best-effort)",
                f"looked for {_display_path(path)}; "
                "if you use a different client, verify wiring manually",
            )
        ]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        if not isinstance(servers, dict):
            servers = {}
    except (OSError, json.JSONDecodeError) as exc:
        return [
            Signal(
                SECTION_WIRING,
                Status.LIMITATION,
                "client config unreadable (best-effort)",
                str(exc),
            )
        ]

    out: list[Signal] = []
    if _has_agent_sudo(servers):
        out.append(
            Signal(SECTION_WIRING, Status.OBSERVED, "agent-sudo registered", _display_path(path))
        )
    else:
        out.append(
            Signal(
                SECTION_WIRING,
                Status.MISCONFIG,
                "agent-sudo not found in client config",
                f"add the agent-sudo MCP server to {_display_path(path)}",
            )
        )

    others = [name for name in servers if not _is_agent_sudo(name, servers[name])]
    if others:
        out.append(
            Signal(
                SECTION_WIRING,
                Status.LIMITATION,
                f"{len(others)} other MCP server(s) present",
                f"{', '.join(sorted(others))} — these may expose tools that "
                "bypass agent-sudo (name-based heuristic, not a capability check)",
            )
        )
    return out


def _has_agent_sudo(servers: dict) -> bool:
    return any(_is_agent_sudo(name, cfg) for name, cfg in servers.items())


def _is_agent_sudo(name: str, cfg: object) -> bool:
    if "agent-sudo" in name.lower() or "agent_sudo" in name.lower():
        return True
    if isinstance(cfg, dict):
        command = str(cfg.get("command", "")).lower()
        if "agent-sudo" in command or "agent_sudo" in command:
            return True
    return False


# --- Trust boundary (always shown) ----------------------------------------


def _boundary_signals() -> list[Signal]:
    return [
        Signal(
            SECTION_BOUNDARY,
            Status.LIMITATION,
            "Native/built-in client tools execute outside agent-sudo and are invisible here",
        ),
        Signal(
            SECTION_BOUNDARY,
            Status.LIMITATION,
            "Only tool calls routed through agent-sudo are gated and audited",
        ),
        Signal(
            SECTION_BOUNDARY,
            Status.LIMITATION,
            "No recent records is not proof of safety — the agent may not have "
            "acted, or may be acting through an unrouted path",
        ),
    ]


# --- Rendering / exit code -------------------------------------------------


def format_routing_report(signals: list[Signal]) -> str:
    lines: list[str] = []
    sections = [SECTION_CONFIG, SECTION_ACTIVITY, SECTION_WIRING, SECTION_BOUNDARY]
    for section in sections:
        section_signals = [s for s in signals if s.section == section]
        if not section_signals:
            continue
        if lines:
            lines.append("")
        lines.append(section)
        for sig in section_signals:
            icon = _ICON[sig.status]
            text = f"  {icon} {sig.label}"
            if sig.detail:
                text += f"\n      {sig.detail}"
            lines.append(text)
    lines.append("")
    lines.append(
        "This command reports observed signals. It cannot certify routing "
        "completeness."
    )
    lines.append(
        "To confirm a specific action was gated, perform it, then run "
        "`agent-sudo audit list`."
    )
    return "\n".join(lines)


def routing_exit_code(signals: list[Signal], *, strict: bool = False) -> int:
    """Informational by default (0). With --strict, non-zero on provable
    misconfiguration only. Structural trust-boundary limits never gate."""
    if not strict:
        return 0
    has_misconfig = any(s.status == Status.MISCONFIG for s in signals)
    return 1 if has_misconfig else 0


def _display_path(path: Path) -> str:
    resolved = path.expanduser()
    home = Path.home()
    try:
        return f"~/{resolved.relative_to(home)}"
    except ValueError:
        return str(resolved)
