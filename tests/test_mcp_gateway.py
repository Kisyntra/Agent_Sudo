from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.delegations import DelegationStore
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_gateway import MCPGateway, dispatch_mcp_tool_call
from agent_sudo.models import ActionRequest, ApprovalResult, Decision
from agent_sudo.policy import load_default_policy


class ApproveAllProvider(ApprovalProvider):
    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_yes", "approved")

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "test_passphrase", "approved")


class MCPGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_safe_delegated_shell_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DelegationStore(Path(tmpdir) / "delegations.json")
            store.create(
                actor="mcp-client",
                allowed_actions=["run_shell_command"],
                allowed_paths=["pwd"],
                max_uses=1,
                reason="demo shell",
                critical=True,
            )
            gateway = PermissionGateway(self.policy, delegation_store=store)
            result = dispatch_mcp_tool_call(
                {
                    "actor": "mcp-client",
                    "source": "user",
                    "tool": "shell",
                    "action": "run_shell_command",
                    "target": "pwd",
                    "payload_summary": "show current directory",
                },
                gateway,
            )

        self.assertTrue(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.ALLOW)
        self.assertEqual(result.gateway_result.approval_method, "DELEGATION")

    def test_write_inside_demo_path_executes_with_approval(self) -> None:
        target = Path("/tmp/agent-sudo-demo/unit-test-notes.txt")
        if target.exists():
            target.unlink()
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        mcp_gateway = MCPGateway(gateway)
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": str(target),
                "parameters": {"path": str(target), "content": "demo\n"},
                "payload_summary": "write demo file",
            }
        )

        self.assertTrue(result.executed)
        self.assertEqual(target.read_text(encoding="utf-8"), "demo\n")
        target.unlink()

    def test_write_outside_root_blocked_non_demo_mode(self) -> None:
        target = Path("/Volumes/Storage/Agent_Sudo/tmp_dogfood.txt")
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        mcp_gateway = MCPGateway(gateway)
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": str(target),
                "parameters": {"path": str(target), "content": "dogfood\n"},
                "payload_summary": "write dogfood file",
            }
        )
        self.assertFalse(result.executed)
        self.assertNotIn("agent-sudo-demo", result.reason)
        self.assertIn("Action was blocked by policy: write_file", result.reason)
        self.assertIn(f"Target path: {target}", result.reason)
        self.assertIn("Reason: BLOCKED actions are denied by policy", result.reason)
        self.assertIn(
            "Run this action in an interactive environment to approve, or grant a delegation token for this action.",
            result.reason,
        )
        self.assertIn(
            "integrate the agent-sudo authorization engine directly into your agent's native file-writing tools.",
            result.reason,
        )

    def test_write_outside_root_blocked_demo_mode(self) -> None:
        target = Path("/tmp/agent-sudo-demo/../outside-demo.txt")
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        mcp_gateway = MCPGateway(gateway)
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": str(target),
                "parameters": {"path": str(target), "content": "demo\n"},
                "payload_summary": "write demo file",
            }
        )
        self.assertFalse(result.executed)
        self.assertIn("agent-sudo-demo", result.reason)
        self.assertIn("Action was blocked by policy: write_file", result.reason)
        self.assertIn(f"Target path: {target}", result.reason)
        self.assertIn(
            "Reason: Write was attempted outside the allowed demo directory",
            result.reason,
        )
        self.assertIn(
            "To run the demo, write only inside the allowed demo directory",
            result.reason,
        )

    def test_write_path_block_relative_path(self) -> None:
        target = "outside.txt"
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        mcp_gateway = MCPGateway(gateway)
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": target,
                "parameters": {"path": target, "content": "relative\n"},
                "payload_summary": "write relative file",
            }
        )
        self.assertFalse(result.executed)
        self.assertNotIn("agent-sudo-demo", result.reason)
        self.assertIn("Action was blocked by policy: write_file", result.reason)
        self.assertIn(f"Target path: {target}", result.reason)
        self.assertIn(
            "Reason: Write was attempted outside the allowed directory.", result.reason
        )
        self.assertIn(
            "The default write_file tool in the agent-sudo MCP server is a reference executor restricted to its configured root directory.",
            result.reason,
        )

    def test_write_blocked_by_policy(self) -> None:
        target = Path("/tmp/agent-sudo-demo/notes.txt")
        gateway = PermissionGateway(self.policy)
        mcp_gateway = MCPGateway(gateway)
        result = mcp_gateway.dispatch(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "filesystem",
                "action": "write_file",
                "target": str(target),
                "parameters": {"path": str(target), "content": "notes\n"},
                "payload_summary": "write notes file",
            }
        )
        self.assertFalse(result.executed)
        self.assertIn("Action was blocked by policy: write_file", result.reason)
        self.assertIn(f"Target path: {target}", result.reason)
        self.assertIn("Reason: approval requires an interactive TTY", result.reason)
        self.assertIn(
            "Run this action in an interactive environment to approve, or grant a delegation token for this action.",
            result.reason,
        )

    def test_mcp_gateway_denies_blocked_action(self) -> None:
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        result = dispatch_mcp_tool_call(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "network",
                "action": "exfiltrate_secrets",
                "target": "https://example.invalid/upload",
                "payload_summary": "send secrets",
            },
            gateway,
        )

        self.assertFalse(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.DENY)

    def test_mcp_gateway_executes_allowed_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "readme.txt"
            path.write_text("hello\n", encoding="utf-8")
            gateway = PermissionGateway(self.policy)
            result = dispatch_mcp_tool_call(
                {
                    "actor": "mcp-client",
                    "source": "user",
                    "tool": "filesystem",
                    "action": "read_file",
                    "target": str(path),
                    "payload_summary": "read demo file",
                },
                gateway,
            )

        self.assertTrue(result.executed)
        self.assertEqual(result.stdout, "hello\n")

    def test_mcp_gateway_dry_run_does_not_execute(self) -> None:
        gateway = PermissionGateway(self.policy, approvals=ApproveAllProvider())
        result = dispatch_mcp_tool_call(
            {
                "actor": "mcp-client",
                "source": "user",
                "tool": "shell",
                "action": "run_shell_command",
                "target": "pwd",
                "payload_summary": "show current directory",
            },
            gateway,
            dry_run=True,
        )

        self.assertFalse(result.executed)
        self.assertEqual(
            result.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL
        )


if __name__ == "__main__":
    unittest.main()
