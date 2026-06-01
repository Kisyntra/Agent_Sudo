from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_sudo._locking import DEFAULT_LOCK_TIMEOUT, file_lock
from agent_sudo.models import GatewayResult
from agent_sudo.spec_helpers import compute_entry_hash, verify_jsonl_file


class AuditLogger:
    def __init__(self, path: Path, *, lock_timeout: float = DEFAULT_LOCK_TIMEOUT):
        self.path = path
        self.lock_timeout = lock_timeout

    @property
    def _lock_path(self) -> Path:
        return Path(str(self.path) + ".lock")

    def record(self, result: GatewayResult) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_type": "gateway_decision",
            **result.to_dict(),
        }
        self._write_entry(entry)

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "event_type": event_type,
            **payload,
        }
        self._write_entry(entry)

    def _write_entry(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Read last hash -> link -> append must be one atomic step, otherwise two
        # concurrent appends read the same previous_hash and fork the chain. The
        # lock (and a torn/corrupt tail raising in _last_entry_hash) keep us
        # fail-closed: on failure we raise rather than write an unchained row.
        with file_lock(self._lock_path, self.lock_timeout):
            previous_hash = _last_entry_hash(self.path)
            entry["previous_hash"] = previous_hash
            entry["entry_hash"] = compute_entry_hash(previous_hash, entry)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


def verify_audit_log(path: Path) -> tuple[bool, str]:
    result = verify_jsonl_file(path)
    if result.success:
        return True, "audit log verified"
    return False, str(result)


def read_audit_entries(path: Path) -> list[dict[str, Any]]:
    """Load audit JSONL records as a list of dicts (oldest first)."""
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def _audit_view(entry: dict[str, Any]) -> dict[str, str]:
    """Reduce a raw audit entry to the human-facing columns.

    Handles both ``gateway_decision`` records (which carry a ``request``) and
    approval lifecycle events (which carry an ``approval_request``).
    """
    event_type = str(entry.get("event_type", "event"))

    request = entry.get("request")
    approval = entry.get("approval_request")
    if not isinstance(request, dict) and isinstance(approval, dict):
        request = approval.get("action_request")
    if not isinstance(request, dict):
        request = {}

    if event_type == "gateway_decision":
        label = str(entry.get("decision", ""))
    else:
        label = event_type

    reason = entry.get("reason")
    if reason is None and isinstance(approval, dict):
        reason = approval.get("reason")

    return {
        "time": str(entry.get("timestamp", ""))[:19],
        "label": label,
        "actor": str(request.get("actor", "")),
        "action": str(request.get("action", "")),
        "target": str(request.get("target", "")),
        "reason": str(reason or ""),
    }


# (column header, width) pairs for the audit table.
_AUDIT_COLUMNS = [
    ("time", 19),
    ("decision", 17),
    ("actor", 12),
    ("action", 20),
    ("target", 22),
    ("reason", 44),
]


def format_audit_log(entries: list[dict[str, Any]], *, limit: int | None = None) -> str:
    """Render audit records as a readable table (newest at the bottom).

    Mirrors the style of ``format_pending_approvals``: a header row followed by
    clipped, space-separated columns. ``limit`` keeps only the most recent N
    records while preserving their original (1-based) record numbers.
    """
    if not entries:
        return "No audit records found."
    selected = entries if not limit or limit <= 0 else entries[-limit:]
    first_number = len(entries) - len(selected) + 1

    header = "  ".join(
        ["#".ljust(4)] + [name.ljust(width) for name, width in _AUDIT_COLUMNS]
    )
    rows = [header]
    for offset, entry in enumerate(selected):
        view = _audit_view(entry)
        cells = [str(first_number + offset).ljust(4)]
        for name, width in _AUDIT_COLUMNS:
            key = "label" if name == "decision" else name
            cells.append(_clip(view[key], width).ljust(width))
        rows.append("  ".join(cells).rstrip())
    return "\n".join(rows)


def _clip(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(0, width - 1)] + "."


GENESIS_HASH = "0" * 64


def _last_entry_hash(path: Path) -> str:
    if not path.exists():
        return GENESIS_HASH
    last_hash = GENESIS_HASH
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            entry = json.loads(line)
            value = entry.get("entry_hash")
            if not isinstance(value, str):
                raise ValueError("existing audit log contains entry without entry_hash")
            last_hash = value
    return last_hash
