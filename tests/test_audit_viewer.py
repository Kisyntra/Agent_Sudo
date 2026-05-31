from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from agent_sudo.audit import (
    AuditLogger,
    format_audit_log,
    read_audit_entries,
)
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import ActionRequest
from agent_sudo.policy import load_default_policy


def _write_log(path: Path) -> None:
    """Produce a real audit log with an ALLOW and a DENY gateway decision."""
    policy = load_default_policy()
    gateway = PermissionGateway(policy, audit_logger=AuditLogger(path))
    gateway.evaluate(
        ActionRequest(
            "mcp-client", "user", "filesystem", "read_file", "README.md", "read"
        )
    )
    gateway.evaluate(
        ActionRequest(
            "web-agent",
            "webpage",
            "network",
            "exfiltrate_secrets",
            "https://attacker.example/leak",
            "upload .env",
        ),
        dry_run=True,
    )


class FormatAuditLogTests(unittest.TestCase):
    def test_empty_entries_message(self) -> None:
        self.assertEqual(format_audit_log([]), "No audit records found.")

    def test_renders_decision_actor_action_target_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            entries = read_audit_entries(path)
            output = format_audit_log(entries)

        # header present
        self.assertIn("decision", output)
        self.assertIn("actor", output)
        self.assertIn("reason", output)
        # both decisions and their fields are visible to a human
        self.assertIn("ALLOW", output)
        self.assertIn("DENY", output)
        self.assertIn("read_file", output)
        self.assertIn("exfiltrate_secrets", output)
        self.assertIn("mcp-client", output)
        # reason text is rendered, not just a hash
        self.assertIn("allowed by policy", output)

    def test_limit_keeps_recent_and_preserves_record_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)  # 2 records
            entries = read_audit_entries(path)
            output = format_audit_log(entries, limit=1)

        rows = [r for r in output.splitlines() if r.strip()]
        # header + exactly one data row
        self.assertEqual(len(rows), 2)
        # the surviving record keeps its original 1-based number (2), not 1
        self.assertTrue(rows[1].startswith("2"))
        self.assertIn("DENY", rows[1])

    def test_handles_approval_lifecycle_event_shape(self) -> None:
        # Events carry an approval_request, not a top-level request.
        entry = {
            "timestamp": "2026-05-31T01:02:03Z",
            "event_type": "approval_denied",
            "approval_request": {
                "reason": "user denied",
                "action_request": {
                    "actor": "codex",
                    "action": "run_shell_command",
                    "target": "rm -rf /",
                },
            },
        }
        output = format_audit_log([entry])
        self.assertIn("approval_denied", output)
        self.assertIn("codex", output)
        self.assertIn("run_shell_command", output)
        self.assertIn("user denied", output)

    def test_malformed_entry_does_not_crash(self) -> None:
        # Missing request/decision keys should degrade gracefully.
        output = format_audit_log([{"event_type": "passphrase_reset"}])
        self.assertIn("passphrase_reset", output)


class ReadAuditEntriesTests(unittest.TestCase):
    def test_missing_file_returns_empty(self) -> None:
        self.assertEqual(read_audit_entries(Path("/no/such/file.jsonl")), [])

    def test_skips_blank_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            path.write_text('{"event_type": "a"}\n\n{"event_type": "b"}\n')
            entries = read_audit_entries(path)
        self.assertEqual([e["event_type"] for e in entries], ["a", "b"])


class AuditListCliTests(unittest.TestCase):
    def test_cli_audit_list_renders_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "list", str(path)])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("ALLOW", out)
        self.assertIn("DENY", out)

    def test_cli_audit_list_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "list", str(path), "--json", "--limit", "1"])
        self.assertEqual(code, 0)
        records = json.loads(buffer.getvalue())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "DENY")

    def test_cli_audit_list_missing_file_errors(self) -> None:
        missing = Path(tempfile.gettempdir()) / "agent-sudo-nonexistent-audit.jsonl"
        if missing.exists():
            missing.unlink()
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["audit", "list", str(missing)])
        self.assertEqual(code, 1)
        self.assertIn("no audit log found", err.getvalue())


if __name__ == "__main__":
    unittest.main()
