from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from agent_sudo.audit import (
    AuditLogger,
    audit_entries_since,
    filter_entries,
    format_audit_log,
    format_audit_review,
    parse_since_window,
    read_audit_entries,
)
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import ActionRequest, TrustLevel
from agent_sudo.policy import load_default_policy


def _write_log(path: Path) -> None:
    """Produce a real audit log with an ALLOW and a DENY gateway decision."""
    policy = load_default_policy()
    gateway = PermissionGateway(policy, audit_logger=AuditLogger(path))
    gateway.evaluate(
        ActionRequest(
            "mcp-client",
            "user",
            "filesystem",
            "read_file",
            "README.md",
            "read",
            source_trust=TrustLevel.USER_DIRECT,
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


class AuditReviewTests(unittest.TestCase):
    def test_parse_since_window(self) -> None:
        self.assertEqual(parse_since_window("30m").total_seconds(), 1800)
        self.assertEqual(parse_since_window("24h").total_seconds(), 86400)
        self.assertEqual(parse_since_window("7d").days, 7)
        with self.assertRaises(ValueError):
            parse_since_window("0h")
        with self.assertRaises(ValueError):
            parse_since_window("yesterday")

    def test_audit_entries_since_filters_by_timestamp(self) -> None:
        entries = [
            {
                "timestamp": "2000-01-01T00:00:00Z",
                "decision": "ALLOW",
            },
            {
                "timestamp": "2999-01-01T00:00:00Z",
                "decision": "DENY",
            },
        ]

        selected = audit_entries_since(entries, parse_since_window("24h"))

        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["decision"], "DENY")

    def test_format_audit_review_counts_and_non_allow_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            entries = read_audit_entries(path)

        output = format_audit_review(entries, since_label="24h")

        self.assertIn("ALLOW: 1", output)
        self.assertIn("DENY: 1", output)
        self.assertIn("Non-ALLOW records:", output)
        self.assertIn("exfiltrate_secrets", output)
        self.assertNotIn("read_file", output.split("Non-ALLOW records:", 1)[1])


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

    def test_cli_audit_review_verifies_chain_and_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "review", str(path), "--since", "24h"])

        self.assertEqual(code, 0)
        output = buffer.getvalue()
        self.assertIn("audit log verified", output)
        self.assertIn("ALLOW: 1", output)
        self.assertIn("DENY: 1", output)
        self.assertIn("Non-ALLOW records:", output)

    def test_cli_audit_review_exits_nonzero_on_tampered_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            _write_log(path)
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"timestamp": "2026-01-01T00:00:00Z"}\n')
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["audit", "review", str(path)])

        self.assertEqual(code, 1)
        self.assertIn("mismatch", err.getvalue())


def _decision_entry(
    decision: str,
    *,
    origin: str = "UNKNOWN",
    actor: str = "claude-code",
    tool: str = "terminal",
    action: str = "run_shell_command",
    target: str = "ls",
) -> dict:
    """A raw gateway_decision audit entry for filter/CLI tests."""
    return {
        "timestamp": "2026-06-02T14:00:00Z",
        "event_type": "gateway_decision",
        "decision": decision,
        "reason": "test record",
        "request": {
            "actor": actor,
            "tool": tool,
            "action": action,
            "target": target,
            "provenance": {"origin_type": origin},
        },
    }


def _write_raw(path: Path, entries: list[dict]) -> None:
    """Write entries as plain JSONL (audit list does not verify the chain)."""
    with path.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps(entry) + "\n")


class FilterEntriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = [
            _decision_entry("ALLOW", origin="USER_DIRECT", actor="claude-code"),
            _decision_entry(
                "DENY",
                origin="EXTERNAL_CONTENT",
                actor="web-agent",
                tool="network",
                target="https://attacker.example/leak",
            ),
            _decision_entry(
                "REQUIRE_APPROVAL",
                origin="AGENT_INTERNAL",
                action="write_file",
                target="src/config.py",
            ),
        ]

    def test_no_filters_is_noop(self) -> None:
        self.assertEqual(filter_entries(self.entries), self.entries)

    def test_filter_by_decision(self) -> None:
        out = filter_entries(self.entries, decision="DENY")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["decision"], "DENY")

    def test_filter_by_origin(self) -> None:
        out = filter_entries(self.entries, origin="EXTERNAL_CONTENT")
        self.assertEqual(len(out), 1)
        self.assertEqual(
            out[0]["request"]["provenance"]["origin_type"], "EXTERNAL_CONTENT"
        )

    def test_non_allow_excludes_allow(self) -> None:
        out = filter_entries(self.entries, non_allow=True)
        self.assertEqual({e["decision"] for e in out}, {"DENY", "REQUIRE_APPROVAL"})

    def test_filter_actor_substring_case_insensitive(self) -> None:
        out = filter_entries(self.entries, actor="WEB")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["request"]["actor"], "web-agent")

    def test_filter_tool_substring(self) -> None:
        out = filter_entries(self.entries, tool="network")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["decision"], "DENY")

    def test_filter_target_substring(self) -> None:
        out = filter_entries(self.entries, target="config.py")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["decision"], "REQUIRE_APPROVAL")

    def test_combined_filters(self) -> None:
        out = filter_entries(self.entries, non_allow=True, origin="EXTERNAL_CONTENT")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["decision"], "DENY")

    def test_no_match_returns_empty(self) -> None:
        self.assertEqual(filter_entries(self.entries, actor="nobody"), [])

    def test_handles_approval_lifecycle_shape(self) -> None:
        event = {
            "timestamp": "2026-06-02T14:00:00Z",
            "event_type": "approval_denied",
            "approval_request": {
                "reason": "user denied",
                "action_request": {
                    "actor": "codex",
                    "provenance": {"origin_type": "USER_DIRECT"},
                },
            },
        }
        # origin resolves through approval_request.action_request; no crash
        self.assertEqual(filter_entries([event], origin="USER_DIRECT"), [event])
        self.assertEqual(filter_entries([event], origin="EXTERNAL_CONTENT"), [])


class AuditViewOriginColumnTests(unittest.TestCase):
    def test_origin_column_in_header_and_rows(self) -> None:
        entries = [_decision_entry("DENY", origin="EXTERNAL_CONTENT")]
        output = format_audit_log(entries)
        self.assertIn("origin", output)
        self.assertIn("EXTERNAL_CONTENT", output)

    def test_existing_columns_preserved(self) -> None:
        output = format_audit_log([_decision_entry("ALLOW", origin="USER_DIRECT")])
        for header in ("time", "decision", "actor", "action", "target", "reason"):
            self.assertIn(header, output)


class CliAuditListFilterTests(unittest.TestCase):
    def _log(self, tmpdir: str) -> Path:
        path = Path(tmpdir) / "audit.jsonl"
        _write_raw(
            path,
            [
                _decision_entry("ALLOW", origin="USER_DIRECT", target="README.md"),
                _decision_entry(
                    "DENY",
                    origin="EXTERNAL_CONTENT",
                    actor="web-agent",
                    target="https://attacker.example/leak",
                ),
            ],
        )
        return path

    def test_origin_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    ["audit", "list", str(path), "--origin", "EXTERNAL_CONTENT"]
                )
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("DENY", out)
        self.assertNotIn("README.md", out)

    def test_decision_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "list", str(path), "--decision", "ALLOW"])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("README.md", out)
        self.assertNotIn("DENY", out)

    def test_non_allow_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "list", str(path), "--non-allow"])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("DENY", out)
        self.assertNotIn("README.md", out)

    def test_json_output_filtered_and_shape_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    ["audit", "list", str(path), "--decision", "DENY", "--json"]
                )
        self.assertEqual(code, 0)
        records = json.loads(buffer.getvalue())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["decision"], "DENY")
        # raw record shape is unchanged by filtering
        self.assertIn("request", records[0])
        self.assertEqual(
            records[0]["request"]["provenance"]["origin_type"], "EXTERNAL_CONTENT"
        )

    def test_invalid_since_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            err = io.StringIO()
            with redirect_stderr(err):
                code = main(["audit", "list", str(path), "--since", "bogus"])
        self.assertEqual(code, 1)
        self.assertIn("--since", err.getvalue())

    def test_no_flags_unchanged_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = self._log(tmpdir)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["audit", "list", str(path)])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        # both records present when no filter is applied
        self.assertIn("README.md", out)
        self.assertIn("DENY", out)


if __name__ == "__main__":
    unittest.main()
