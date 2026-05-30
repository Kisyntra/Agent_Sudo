from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider, hash_passphrase
from agent_sudo.audit import AuditLogger
from agent_sudo.builders import AgentActionRequest
from agent_sudo.executors import ExecutionResult, SafeToolExecutor
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest, Decision, GatewayResult, TrustLevel
from agent_sudo.policy import load_default_policy


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[ActionRequest] = []

    def execute(self, request: ActionRequest) -> ExecutionResult:
        raise AssertionError("must be called through SafeToolExecutor")

    def dry_run(self, request: ActionRequest) -> ExecutionResult:
        raise AssertionError("must be called through SafeToolExecutor")

    def execute_with_gateway_result(
        self,
        request: ActionRequest,
        gateway_result: GatewayResult,
    ) -> ExecutionResult:
        self.calls.append(request)
        return ExecutionResult(
            request, gateway_result, True, 0, stdout="ok", reason="executed"
        )


class ApprovalHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def _config_path(self, tmpdir: str, passphrase: str = "test-passphrase") -> Path:
        path = Path(tmpdir) / "config.json"
        path.write_text(
            json.dumps(hash_passphrase(passphrase, salt=b"0" * 16)), encoding="utf-8"
        )
        return path

    def test_critical_approval_lockout_after_failed_attempts(self) -> None:
        now = 1000.0
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                lockout_path=Path(tmpdir) / "approval_state.json",
                getpass_func=lambda prompt: "wrong-passphrase",
                stdin_is_tty=lambda: True,
                now_func=lambda: now,
                lockout_seconds=60,
            )
            gateway = PermissionGateway(self.policy, approvals=provider)

            first = gateway.evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )
            second = gateway.evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )
            third = gateway.evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )
            locked = gateway.evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )

        self.assertEqual(first.decision, Decision.DENY)
        self.assertEqual(second.decision, Decision.DENY)
        self.assertEqual(third.decision, Decision.DENY)
        self.assertEqual(locked.decision, Decision.DENY)
        self.assertIn("locked", third.reason)
        self.assertIn("locked", locked.reason)

    def test_critical_action_denied_without_tty_by_not_executing(self) -> None:
        provider = ApprovalProvider(stdin_is_tty=lambda: False)
        gateway = PermissionGateway(self.policy, approvals=provider)
        inner = RecordingExecutor()
        executor = SafeToolExecutor(gateway, inner)

        result = executor.execute(
            AgentActionRequest.send_email("recipient@example.invalid")
        )

        self.assertFalse(result.executed)
        self.assertEqual(
            result.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL
        )
        self.assertEqual(result.gateway_result.approval_method, "PASSPHRASE_CONFIRM")
        self.assertTrue(result.gateway_result.approval_attempts[0]["pending"])
        self.assertEqual(len(inner.calls), 0)

    def test_critical_action_approved_with_correct_passphrase_mock(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            result = PermissionGateway(self.policy, approvals=provider).evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )

        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertEqual(result.approval_method, "PASSPHRASE_CONFIRM")

    def test_critical_action_denied_with_wrong_passphrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "wrong-passphrase",
                stdin_is_tty=lambda: True,
            )
            result = PermissionGateway(self.policy, approvals=provider).evaluate(
                AgentActionRequest.send_email("recipient@example.invalid")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.approval_method, "PASSPHRASE_CONFIRM")

    def test_sensitive_action_can_use_cli_confirm(self) -> None:
        provider = ApprovalProvider(
            input_func=lambda prompt: "yes", stdin_is_tty=lambda: True
        )
        result = PermissionGateway(self.policy, approvals=provider).evaluate(
            AgentActionRequest.file_edit("README.md")
        )

        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertEqual(result.approval_method, "CLI_CONFIRM")

    def test_external_content_cannot_approve_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            gateway = PermissionGateway(self.policy, approvals=provider)
            inner = RecordingExecutor()
            executor = SafeToolExecutor(gateway, inner)
            request = AgentActionRequest.file_edit(
                "README.md",
                source="webpage",
                source_trust=TrustLevel.EXTERNAL_CONTENT,
            )

            result = executor.execute(request)

        self.assertFalse(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.DENY)
        self.assertEqual(result.gateway_result.approval_method, "DENY")
        self.assertEqual(len(inner.calls), 0)

    def test_approval_attempts_appear_in_audit_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            provider = ApprovalProvider(
                input_func=lambda prompt: "yes", stdin_is_tty=lambda: True
            )
            gateway = PermissionGateway(
                self.policy,
                approvals=provider,
                audit_logger=AuditLogger(audit_path),
            )
            gateway.evaluate(AgentActionRequest.file_edit("README.md"))

            entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(entry["approval_attempts"][0]["method"], "CLI_CONFIRM")
        self.assertTrue(entry["approval_attempts"][0]["approved"])


if __name__ == "__main__":
    unittest.main()
