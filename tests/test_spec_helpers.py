from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_sudo.spec_helpers import (
    canonicalize_record,
    compute_entry_hash,
    verify_hash_chain,
    verify_jsonl_file,
)
from agent_sudo.audit import AuditLogger


class SpecHelpersTests(unittest.TestCase):

    def test_canonical_json_sorting(self) -> None:
        # Key sorting should be alphabetical at all levels of nesting
        record = {
            "z": 1,
            "a": {
                "y": 2,
                "b": 3,
            },
            "c": [
                {"x": 4, "d": 5},
                6,
            ]
        }
        res_bytes = canonicalize_record(record)
        res_str = res_bytes.decode("utf-8")

        # Verify serialization details (keys sorted, no spaces)
        expected = '{"a":{"b":3,"y":2},"c":[{"d":5,"x":4},6],"z":1}'
        self.assertEqual(res_str, expected)

    def test_stable_byte_output(self) -> None:
        # Output should be bytes type
        record = {"foo": "bar", "baz": 42}
        res1 = canonicalize_record(record)
        res2 = canonicalize_record(record)

        self.assertIsInstance(res1, bytes)
        self.assertEqual(res1, res2)

    def test_sha256_computation(self) -> None:
        previous_hash = "0" * 64
        record = {
            "timestamp": "2026-05-28T06:00:00Z",
            "event_type": "test_event",
            "previous_hash": previous_hash,
        }

        entry_hash = compute_entry_hash(previous_hash, record)
        self.assertEqual(len(entry_hash), 64)
        # Verify it is a valid hex string
        int(entry_hash, 16)

        # Calculate manually to verify exact match
        import hashlib
        clean = {"timestamp": "2026-05-28T06:00:00Z", "event_type": "test_event", "previous_hash": previous_hash}
        canonical_bytes = json.dumps(clean, sort_keys=True, separators=(",", ":")).encode("utf-8")
        concatenated = previous_hash.encode("utf-8") + canonical_bytes
        expected = hashlib.sha256(concatenated).hexdigest()
        self.assertEqual(entry_hash, expected)

    def test_valid_jsonl_chain_verification(self) -> None:
        previous_hash = "0" * 64
        records = []
        for i in range(3):
            record = {
                "index": i,
                "previous_hash": previous_hash,
            }
            entry_hash = compute_entry_hash(previous_hash, record)
            record["entry_hash"] = entry_hash
            records.append(record)
            previous_hash = entry_hash

        result = verify_hash_chain(records)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "verification succeeded")

        # Verify through JSONL file
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "test.jsonl"
            with file_path.open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r) + "\n")

            file_result = verify_jsonl_file(file_path)
            self.assertTrue(file_result.success)
            self.assertEqual(file_result.reason, "audit log verified")

    def test_tampered_record_detection(self) -> None:
        previous_hash = "0" * 64
        records = []
        for i in range(3):
            record = {
                "index": i,
                "previous_hash": previous_hash,
            }
            entry_hash = compute_entry_hash(previous_hash, record)
            record["entry_hash"] = entry_hash
            records.append(record)
            previous_hash = entry_hash

        # Tamper with the second record
        records[1]["index"] = 999

        result = verify_hash_chain(records)
        self.assertFalse(result.success)
        self.assertEqual(result.line_number, 2)
        self.assertEqual(result.reason, "entry_hash mismatch")

    def test_wrong_previous_hash_detection(self) -> None:
        previous_hash = "0" * 64
        records = []
        for i in range(3):
            record = {
                "index": i,
                "previous_hash": previous_hash,
            }
            entry_hash = compute_entry_hash(previous_hash, record)
            record["entry_hash"] = entry_hash
            records.append(record)
            previous_hash = entry_hash

        # Corrupt the previous_hash link of the third record
        records[2]["previous_hash"] = "badhash" * 8

        result = verify_hash_chain(records)
        self.assertFalse(result.success)
        self.assertEqual(result.line_number, 3)
        self.assertEqual(result.reason, "previous_hash mismatch")

    def test_unknown_extension_field_behavior(self) -> None:
        previous_hash = "0" * 64
        # Add an extension field 'lexflow_session_id'
        record = {
            "timestamp": "2026-05-28T06:00:00Z",
            "event_type": "decision",
            "previous_hash": previous_hash,
            "lexflow_session_id": "lf_abc123",
        }
        entry_hash = compute_entry_hash(previous_hash, record)
        record["entry_hash"] = entry_hash

        # Verify it succeeds when the extension field is intact
        result = verify_hash_chain([record])
        self.assertTrue(result.success)

        # If the extension field is modified, it should fail
        record_modified = record.copy()
        record_modified["lexflow_session_id"] = "lf_xyz789"
        result_modified = verify_hash_chain([record_modified])
        self.assertFalse(result_modified.success)
        self.assertEqual(result_modified.reason, "entry_hash mismatch")

    def test_lexflow_style_minimal_verification(self) -> None:
        # Ensure a minimal LexFlow-style AuditRecord can be verified
        previous_hash = "0" * 64
        record = {
            "timestamp": "2026-05-28T13:20:00Z",
            "event_type": "gateway_decision",
            "request": {
                "actor": "lexflow-desktop",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": "/docs/contract.pdf",
                "payload_summary": "Save PDF",
                "source_trust": "USER_DIRECT",
            },
            "decision": "ALLOW",
            "classification": "SAFE",
            "reason": "user approved",
            "approval_method": "none",
            "previous_hash": previous_hash,
        }
        entry_hash = compute_entry_hash(previous_hash, record)
        record["entry_hash"] = entry_hash

        result = verify_hash_chain([record])
        self.assertTrue(result.success)

    def test_existing_agent_sudo_audit_log_compatibility(self) -> None:
        # Verify that generating a log using the real AuditLogger verifies successfully with verify_jsonl_file
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "audit.jsonl"
            logger = AuditLogger(log_path)

            # Record some dummy events
            logger.record_event("test_event_1", {"msg": "hello"})
            logger.record_event("test_event_2", {"msg": "world", "status": "active"})

            result = verify_jsonl_file(log_path)
            self.assertTrue(result.success)
            self.assertEqual(result.reason, "audit log verified")

    def test_interop_reference_assets_valid(self) -> None:
        # Verify that the reference_log.jsonl file under docs/interop/ verifies successfully
        proj_root = Path(__file__).parent.parent
        log_path = proj_root / "docs" / "interop" / "reference_log.jsonl"
        self.assertTrue(log_path.exists(), f"reference_log.jsonl not found at {log_path}")

        result = verify_jsonl_file(log_path)
        self.assertTrue(result.success, f"reference_log.jsonl verification failed: {result.reason}")

        # Verify reference_record.json contents and hash
        record_path = proj_root / "docs" / "interop" / "reference_record.json"
        self.assertTrue(record_path.exists(), f"reference_record.json not found at {record_path}")
        with record_path.open("r", encoding="utf-8") as f:
            record = json.load(f)
        
        # Strip entry_hash to calculate it canonically
        expected_entry_hash = "99724c0c0b82a195d11f26b15932ba5a1e97b5b4ee90d788f24b0731fe3f59f7"
        self.assertEqual(record.get("entry_hash"), expected_entry_hash)
        computed_hash = compute_entry_hash(record.get("previous_hash", "0" * 64), record)
        self.assertEqual(computed_hash, expected_entry_hash)


if __name__ == "__main__":
    unittest.main()
