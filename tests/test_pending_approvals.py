from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider, hash_passphrase
from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.mcp_gateway import dispatch_mcp_tool_call
from agent_sudo.models import ApprovalStatus, Decision
from agent_sudo.pending_approvals import PendingApprovalStore
from agent_sudo.policy import load_default_policy


class PendingApprovalWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def _critical_tool_call(self) -> dict[str, str]:
        return {
            "actor": "mcp-client",
            "source": "user",
            "tool": "shell",
            "action": "run_shell_command",
            "target": "pwd",
            "payload_summary": "show current directory",
        }

    def _config_path(self, tmpdir: str, passphrase: str = "test-passphrase") -> Path:
        path = Path(tmpdir) / "config.json"
        path.write_text(json.dumps(hash_passphrase(passphrase, salt=b"1" * 16)), encoding="utf-8")
        return path

    def test_non_interactive_mcp_critical_action_creates_pending_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            store = PendingApprovalStore(Path(tmpdir) / "pending.json", audit_logger=AuditLogger(audit_path))
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )

            result = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approvals = store.list()

        self.assertFalse(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0].status, ApprovalStatus.PENDING)
        self.assertEqual(result.gateway_result.approval_request_id, approvals[0].approval_request_id)
        self.assertIn("agent-sudo approve", result.gateway_result.approval_command)

    def test_approval_list_shows_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(["approvals", "list", "--pending-approvals-file", str(pending_path)])

        self.assertEqual(code, 0)
        self.assertIn("run_shell_command", output.getvalue())
        self.assertIn("PENDING", output.getvalue())

    def test_approve_with_passphrase_marks_approved_retry_executes_once_then_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path, audit_logger=AuditLogger(audit_path))
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approval_id = initial.gateway_result.approval_request_id
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            approved, approval_result = store.approve(approval_id, approval_provider=provider)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            second_retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            audit_events = [
                json.loads(line)["event_type"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(approval_result.approved)
        self.assertIsNotNone(approved)
        self.assertEqual(approved.status, ApprovalStatus.APPROVED)
        self.assertTrue(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.ALLOW)
        self.assertEqual(retry.gateway_result.approval_method, "PENDING_APPROVAL")
        self.assertFalse(second_retry.executed)
        self.assertEqual(second_retry.gateway_result.decision, Decision.DENY)
        self.assertIn("USED", second_retry.reason)
        self.assertIn("approval_created", audit_events)
        self.assertIn("approval_approved", audit_events)
        self.assertIn("approval_used", audit_events)
        self.assertEqual(audit_events.count("gateway_decision"), 3)

    def test_retry_with_new_request_id_uses_approved_request_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            first_call = dict(self._critical_tool_call(), request_id="jsonrpc-1")
            retry_call = dict(self._critical_tool_call(), request_id="jsonrpc-2")
            initial = dispatch_mcp_tool_call(first_call, gateway)
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            store.approve(initial.gateway_result.approval_request_id, approval_provider=provider)
            retry = dispatch_mcp_tool_call(retry_call, gateway)
            second_retry = dispatch_mcp_tool_call(retry_call, gateway)

        self.assertTrue(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.ALLOW)
        self.assertFalse(second_retry.executed)
        self.assertEqual(second_retry.gateway_result.decision, Decision.DENY)

    def test_denial_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            denied = store.deny(initial.gateway_result.approval_request_id)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)

        self.assertIsNotNone(denied)
        self.assertEqual(denied.status, ApprovalStatus.DENIED)
        self.assertFalse(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.DENY)
        self.assertIn("DENIED", retry.reason)

    def test_expiration_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path, ttl_seconds=-1)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approvals = store.list()

        self.assertFalse(initial.executed)
        self.assertFalse(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.DENY)
        self.assertIn("EXPIRED", retry.reason)
        self.assertEqual(approvals[0].status, ApprovalStatus.EXPIRED)

    def test_audit_logs_denied_and_expired_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            store = PendingApprovalStore(
                Path(tmpdir) / "pending.json",
                audit_logger=AuditLogger(audit_path),
                ttl_seconds=-1,
            )
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            store.deny(initial.gateway_result.approval_request_id)
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            events = [
                json.loads(line)["event_type"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertIn("approval_created", events)
        self.assertIn("approval_denied", events)
        self.assertIn("gateway_decision", events)


if __name__ == "__main__":
    unittest.main()
