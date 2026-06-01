"""Tests for the read-only `agent-sudo verify-routing` evidence reporter."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_sudo.audit import AuditLogger
from agent_sudo.routing_check import (
    SECTION_BOUNDARY,
    Status,
    format_routing_report,
    routing_exit_code,
    run_routing_check,
)

# Phrases the command must never emit — it cannot prove protection.
FORBIDDEN_PHRASES = [
    "you are protected",
    "you're protected",
    "fully protected",
    "you are safe",
    "you're safe",
    "guaranteed",
    "guarantee protection",
]


def _nonexistent(tmp: Path) -> Path:
    return tmp / "does-not-exist.json"


def _write_valid_audit_log(path: Path, decisions: list[str]) -> None:
    logger = AuditLogger(path)
    for decision in decisions:
        logger.record_event(
            "gateway_decision",
            {"decision": decision, "request": {"actor": "agent"}},
        )


def _write_client_config(path: Path, servers: dict) -> None:
    path.write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")


def _labels(signals, section=None) -> list[str]:
    return [s.label for s in signals if section is None or s.section == section]


class RoutingCheckTests(unittest.TestCase):
    def _run(self, tmp: Path, **overrides):
        defaults = dict(
            repo_root=tmp,
            approval_config_path=_nonexistent(tmp),
            workspace_config_path=_nonexistent(tmp),
            audit_paths=[tmp / "mcp-audit.jsonl"],
            client_config_path=_nonexistent(tmp),
        )
        defaults.update(overrides)
        return run_routing_check(**defaults)

    # 1. never claims protection
    def test_output_has_no_forbidden_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            _write_valid_audit_log(audit, ["ALLOW", "DENY"])
            client = tmp / "client.json"
            _write_client_config(
                client,
                {"agent-sudo": {"command": "agent-sudo-mcp"}, "filesystem": {}},
            )
            signals = self._run(tmp, audit_paths=[audit], client_config_path=client)
            report = format_routing_report(signals).lower()
        for phrase in FORBIDDEN_PHRASES:
            self.assertNotIn(phrase, report, f"forbidden phrase present: {phrase!r}")
        # and there is no aggregate PASS verdict (note: "bypass" is expected)
        self.assertNotIn("all checks passed", report)
        self.assertNotIn("passed", report)

    # 2. no audit records yet (empty log)
    def test_no_requests_observed_yet(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            audit.write_text("", encoding="utf-8")
            signals = self._run(tmp, audit_paths=[audit])
        self.assertIn("no requests observed yet", _labels(signals))
        self.assertEqual(routing_exit_code(signals), 0)

    # 3. audit records observed (with histogram)
    def test_requests_observed_with_histogram(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            _write_valid_audit_log(audit, ["ALLOW", "ALLOW", "DENY"])
            signals = self._run(tmp, audit_paths=[audit])
            report = format_routing_report(signals)
        self.assertIn("requests observed", _labels(signals))
        self.assertIn("3 records", report)
        self.assertIn("ALLOW 2", report)
        self.assertIn("DENY 1", report)

    # 4a. missing audit log
    def test_missing_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            signals = self._run(tmp, audit_paths=[tmp / "nope.jsonl"])
        self.assertIn("no audit log found yet", _labels(signals))

    # 4b. invalid / tampered audit log -> integrity FAILED but still parsed
    def test_invalid_audit_log_integrity_failed(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            # Parseable JSON line but no valid hash chain.
            audit.write_text(
                json.dumps({"event_type": "gateway_decision", "decision": "ALLOW"})
                + "\n",
                encoding="utf-8",
            )
            signals = self._run(tmp, audit_paths=[audit])
        labels = _labels(signals)
        self.assertIn("audit integrity check FAILED", labels)

    # 7. audit hash verification result shown (success case)
    def test_audit_integrity_verified_shown(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            _write_valid_audit_log(audit, ["ALLOW"])
            signals = self._run(tmp, audit_paths=[audit])
        self.assertIn("audit integrity verified", _labels(signals))

    # 5. other MCP servers present
    def test_other_mcp_servers_present(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            client = tmp / "client.json"
            _write_client_config(
                client,
                {
                    "agent-sudo": {"command": "agent-sudo-mcp"},
                    "filesystem": {"command": "mcp-fs"},
                    "shell-runner": {"command": "mcp-shell"},
                },
            )
            signals = self._run(tmp, client_config_path=client)
            report = format_routing_report(signals)
        self.assertIn("agent-sudo registered", _labels(signals))
        self.assertTrue(
            any("other MCP server" in label for label in _labels(signals))
        )
        self.assertIn("filesystem", report)
        self.assertIn("shell-runner", report)

    # 6. Agent_Sudo missing from client config
    def test_agent_sudo_missing_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            client = tmp / "client.json"
            _write_client_config(client, {"filesystem": {"command": "mcp-fs"}})
            signals = self._run(tmp, client_config_path=client)
        self.assertIn("agent-sudo not found in client config", _labels(signals))
        self.assertEqual(routing_exit_code(signals, strict=True), 1)

    # missing client config is neutral, not an error
    def test_missing_client_config_is_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            signals = self._run(tmp, client_config_path=tmp / "absent.json")
        self.assertTrue(
            any("client config not found" in label for label in _labels(signals))
        )

    # trust-boundary block always present, even with a healthy setup
    def test_trust_boundary_always_shown(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            audit = tmp / "mcp-audit.jsonl"
            _write_valid_audit_log(audit, ["ALLOW"])
            client = tmp / "client.json"
            _write_client_config(client, {"agent-sudo": {"command": "agent-sudo-mcp"}})
            signals = self._run(tmp, audit_paths=[audit], client_config_path=client)
        boundary = [s for s in signals if s.section == SECTION_BOUNDARY]
        self.assertEqual(len(boundary), 3)
        self.assertTrue(all(s.status == Status.LIMITATION for s in boundary))

    # default exit code is informational (0) even with misconfig/warnings
    def test_default_exit_code_is_informational(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            signals = self._run(tmp)  # nothing configured -> misconfig present
        self.assertEqual(routing_exit_code(signals), 0)
        self.assertEqual(routing_exit_code(signals, strict=True), 1)


if __name__ == "__main__":
    unittest.main()
