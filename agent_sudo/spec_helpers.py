from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class VerificationResult:
    """Represents the structured result of an audit log verification."""

    def __init__(
        self,
        success: bool,
        line_number: int | None = None,
        expected_hash: str | None = None,
        actual_hash: str | None = None,
        reason: str | None = None,
    ):
        self.success = success
        self.line_number = line_number
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.reason = reason

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        if self.success:
            return self.reason or "verification succeeded"
        prefix = f"line {self.line_number}: " if self.line_number is not None else ""
        return f"{prefix}{self.reason}"


def canonicalize_record(record: dict[str, Any]) -> bytes:
    """Serializes a record canonically, excluding the entry_hash key, returning UTF-8 encoded bytes.

    All object keys at all levels of nesting are sorted alphabetically.
    """
    clean = {k: v for k, v in record.items() if k != "entry_hash"}
    canonical_str = json.dumps(clean, sort_keys=True, separators=(",", ":"))
    return canonical_str.encode("utf-8")


def compute_entry_hash(previous_hash: str, record: dict[str, Any]) -> str:
    """Computes the SHA-256 entry hash using canonical rules."""
    canonical_bytes = canonicalize_record(record)
    concatenated = previous_hash.encode("utf-8") + canonical_bytes
    return hashlib.sha256(concatenated).hexdigest()


def verify_hash_chain(records: Iterable[dict[str, Any]]) -> VerificationResult:
    """Validates the hash chain sequence of an iterable of record objects."""
    previous_hash = "0" * 64
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            return VerificationResult(
                success=False,
                line_number=index,
                reason="Record is not a JSON object",
            )

        expected_prev = record.get("previous_hash")
        if expected_prev != previous_hash:
            return VerificationResult(
                success=False,
                line_number=index,
                expected_hash=previous_hash,
                actual_hash=expected_prev,
                reason="previous_hash mismatch",
            )

        actual_hash = record.get("entry_hash")
        if not actual_hash:
            return VerificationResult(
                success=False,
                line_number=index,
                reason="Missing entry_hash",
            )

        expected_hash = compute_entry_hash(previous_hash, record)
        if actual_hash != expected_hash:
            return VerificationResult(
                success=False,
                line_number=index,
                expected_hash=expected_hash,
                actual_hash=actual_hash,
                reason="entry_hash mismatch",
            )
        previous_hash = actual_hash

    return VerificationResult(success=True, reason="verification succeeded")


def verify_jsonl_file(path: Path) -> VerificationResult:
    """Reads a JSONL log file and validates its canonical hash chain."""
    previous_hash = "0" * 64
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    return VerificationResult(
                        success=False,
                        line_number=line_number,
                        reason=f"invalid JSON: {exc}",
                    )

                if not isinstance(record, dict):
                    return VerificationResult(
                        success=False,
                        line_number=line_number,
                        reason="line is not a JSON object",
                    )

                expected_prev = record.get("previous_hash")
                if expected_prev != previous_hash:
                    return VerificationResult(
                        success=False,
                        line_number=line_number,
                        expected_hash=previous_hash,
                        actual_hash=expected_prev,
                        reason="previous_hash mismatch",
                    )

                actual_hash = record.get("entry_hash")
                expected_hash = compute_entry_hash(previous_hash, record)
                if actual_hash != expected_hash:
                    return VerificationResult(
                        success=False,
                        line_number=line_number,
                        expected_hash=expected_hash,
                        actual_hash=actual_hash,
                        reason="entry_hash mismatch",
                    )
                previous_hash = actual_hash
    except Exception as exc:
        return VerificationResult(
            success=False,
            reason=f"Failed to read file: {exc}",
        )
    return VerificationResult(success=True, reason="audit log verified")
