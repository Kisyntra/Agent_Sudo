from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_validation import (
    discover_hermes_mcp,
    jsonrpc_tool_call,
    run_jsonrpc_case,
)
from agent_sudo.models import ActionRequest, ApprovalResult
from agent_sudo.policy import load_default_policy


class ApproveAllProvider(ApprovalProvider):
    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_yes", "approved")

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_passphrase", "approved")


class RealMCPIntegrationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_hermes_mcp_discovery_reports_available_implementation(self) -> None:
        discovery = discover_hermes_mcp()

        self.assertEqual(discovery["implementation"], "hermes")
        self.assertIn("hermes_available", discovery)
        self.assertIn("servers", discovery)

    def test_case_a_read_file_allowed_and_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            target = Path(tmpdir) / "sample.txt"
            target.write_text("read ok\n", encoding="utf-8")
            transcript = run_jsonrpc_case(
                jsonrpc_tool_call("case-a", "read_file", {"path": str(target)}),
                policy=self.policy,
                audit_path=audit_path,
            )

        self.assertEqual(transcript["classification"], "SAFE")
        self.assertEqual(transcript["approval_decision"], "ALLOW")
        self.assertTrue(transcript["execution_result"]["executed"])
        self.assertEqual(transcript["execution_result"]["stdout"], "read ok\n")
        self.assertEqual(transcript["audit_entry"]["decision"], "ALLOW")

    def test_case_b_write_file_requires_approval_and_succeeds_when_approved(
        self,
    ) -> None:
        target = Path("/tmp/agent-sudo-demo/test.txt")
        if target.exists():
            target.unlink()
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            gateway = PermissionGateway(
                self.policy,
                approvals=ApproveAllProvider(),
                audit_logger=AuditLogger(audit_path),
            )
            transcript = run_jsonrpc_case(
                jsonrpc_tool_call(
                    "case-b",
                    "write_file",
                    {"path": str(target), "content": "write ok\n"},
                ),
                policy=self.policy,
                audit_path=audit_path,
                gateway=gateway,
            )

        self.assertEqual(transcript["classification"], "SENSITIVE")
        self.assertEqual(transcript["approval_decision"], "ALLOW")
        self.assertEqual(transcript["approval_method"], "test_yes")
        self.assertTrue(transcript["execution_result"]["executed"])
        self.assertEqual(target.read_text(encoding="utf-8"), "write ok\n")
        self.assertEqual(transcript["audit_entry"]["approval_method"], "test_yes")
        target.unlink()

    def test_case_c_write_file_to_ssh_config_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            transcript = run_jsonrpc_case(
                jsonrpc_tool_call(
                    "case-c",
                    "write_file",
                    {"path": "~/.ssh/config", "content": "blocked\n"},
                ),
                policy=self.policy,
                audit_path=Path(tmpdir) / "audit.jsonl",
            )

        self.assertEqual(transcript["classification"], "BLOCKED")
        self.assertEqual(transcript["approval_decision"], "DENY")
        self.assertFalse(transcript["execution_result"]["executed"])

    def test_case_d_pwd_shell_is_critical_and_requires_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = ApprovalProvider(stdin_is_tty=lambda: False)
            gateway = PermissionGateway(
                self.policy,
                approvals=provider,
                audit_logger=AuditLogger(Path(tmpdir) / "audit.jsonl"),
            )
            transcript = run_jsonrpc_case(
                jsonrpc_tool_call("case-d", "run_shell_command", {"command": "pwd"}),
                policy=self.policy,
                audit_path=Path(tmpdir) / "audit.jsonl",
                gateway=gateway,
            )

        self.assertEqual(transcript["classification"], "CRITICAL")
        self.assertEqual(transcript["approval_decision"], "REQUIRE_STRONG_APPROVAL")
        self.assertFalse(transcript["execution_result"]["executed"])

    def test_case_e_destructive_shell_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = PermissionGateway(
                self.policy,
                approvals=ApproveAllProvider(),
                audit_logger=AuditLogger(Path(tmpdir) / "audit.jsonl"),
            )
            transcript = run_jsonrpc_case(
                jsonrpc_tool_call(
                    "case-e", "run_shell_command", {"command": "rm -rf /"}
                ),
                policy=self.policy,
                audit_path=Path(tmpdir) / "audit.jsonl",
                gateway=gateway,
            )

        self.assertEqual(transcript["classification"], "BLOCKED")
        self.assertEqual(transcript["approval_decision"], "DENY")
        self.assertFalse(transcript["execution_result"]["executed"])


if __name__ == "__main__":
    unittest.main()
