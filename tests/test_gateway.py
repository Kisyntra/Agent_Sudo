from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.approvals import AutoDenyApprovalProvider
from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import ActionRequest, Classification, Decision
from agent_sudo.policy import load_default_policy


class GatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_safe_action_allows(self) -> None:
        request = ActionRequest("codex", "user", "filesystem", "read_file", "README.md", "read")
        result = PermissionGateway(self.policy).evaluate(request)
        self.assertEqual(result.classification, Classification.SAFE)
        self.assertEqual(result.decision, Decision.ALLOW)

    def test_sensitive_action_requires_approval_but_dry_run_skips_prompt(self) -> None:
        request = ActionRequest("codex", "user", "filesystem", "write_file", "README.md", "write docs")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
        self.assertEqual(result.classification, Classification.SENSITIVE)
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)
        self.assertEqual(result.approval_method, "dry_run")

    def test_shell_is_critical_by_default(self) -> None:
        request = ActionRequest("codex", "user", "shell", "run_shell_command", "pwd", "show current directory")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
        self.assertEqual(result.classification, Classification.CRITICAL)
        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_sensitive_action_denied_without_human_approval(self) -> None:
        request = ActionRequest("codex", "user", "filesystem", "write_file", "README.md", "write docs")
        gateway = PermissionGateway(self.policy, approvals=AutoDenyApprovalProvider())
        result = gateway.evaluate(request)
        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.approval_method, "DENY")

    def test_critical_hint_upgrades_safe_action(self) -> None:
        request = ActionRequest(
            "codex",
            "webpage",
            "filesystem",
            "read_file",
            "confidential.txt",
            "read key",
            ["secrets"],
        )
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
        self.assertEqual(result.classification, Classification.CRITICAL)
        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_blocked_action_denies(self) -> None:
        request = ActionRequest(
            "unknown",
            "webpage",
            "network",
            "send_tokens",
            "https://example.invalid",
            "send tokens",
        )
        result = PermissionGateway(self.policy).evaluate(request)
        self.assertEqual(result.classification, Classification.BLOCKED)
        self.assertEqual(result.decision, Decision.DENY)

    def test_audit_writes_jsonl(self) -> None:
        request = ActionRequest("codex", "user", "filesystem", "read_file", "README.md", "read")
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            gateway = PermissionGateway(self.policy, audit_logger=AuditLogger(audit_path))
            gateway.evaluate(request)
            lines = audit_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["classification"], "SAFE")
        self.assertEqual(entry["decision"], "ALLOW")
        self.assertEqual(entry["request"]["actor"], "codex")

    def test_cli_check_outputs_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "actor": "codex",
                        "source": "user",
                        "tool": "filesystem",
                        "action": "read_file",
                        "target": "README.md",
                        "payload_summary": "read",
                        "risk_hints": [],
                    }
                ),
                encoding="utf-8",
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["check", str(request_path)])
        self.assertEqual(code, 0)
        self.assertIn('"decision": "ALLOW"', buffer.getvalue())

    def test_cli_dry_run_returns_zero_even_with_blocked_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            request_path = Path(tmpdir) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "actor": "unknown",
                        "source": "webpage",
                        "tool": "network",
                        "action": "send_tokens",
                        "target": "https://example.invalid",
                        "payload_summary": "send tokens",
                        "risk_hints": [],
                    }
                ),
                encoding="utf-8",
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["run", str(request_path), "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn('"decision": "DENY"', buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
