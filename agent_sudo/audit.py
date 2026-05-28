from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_sudo.models import GatewayResult
from agent_sudo.spec_helpers import compute_entry_hash, verify_jsonl_file


class AuditLogger:
    def __init__(self, path: Path):
        self.path = path

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
        previous_hash = _last_entry_hash(self.path)
        entry["previous_hash"] = previous_hash
        entry["entry_hash"] = compute_entry_hash(previous_hash, entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")


def verify_audit_log(path: Path) -> tuple[bool, str]:
    result = verify_jsonl_file(path)
    if result.success:
        return True, "audit log verified"
    return False, str(result)


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
