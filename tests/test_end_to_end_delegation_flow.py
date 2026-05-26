from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.audit import AuditLogger
from agent_sudo.delegations import DelegationStore
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_gateway import dispatch_mcp_tool_call
from agent_sudo.models import Decision
from agent_sudo.policy import load_default_policy


class EndToEndDelegationFlowTests(unittest.TestCase):
    def test_shell_delegation_allows_once_then_exhausts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            delegation_store = DelegationStore(Path(tmpdir) / "delegations.json")
            gateway = PermissionGateway(
                load_default_policy(),
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                delegation_store=delegation_store,
            )
            tool_call = {
                "actor": "codex",
                "source": "user",
                "tool": "shell",
                "action": "run_shell_command",
                "target": "pwd",
                "payload_summary": "show current directory",
            }

            initial = dispatch_mcp_tool_call(tool_call, gateway)
            delegation_store.create(
                actor="codex",
                allowed_actions=["run_shell_command"],
                allowed_paths=["pwd"],
                max_uses=1,
                reason="single pwd validation",
                critical=True,
            )
            delegated = dispatch_mcp_tool_call(tool_call, gateway)
            exhausted = dispatch_mcp_tool_call(tool_call, gateway)

            audit_entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]

        self.assertFalse(initial.executed)
        self.assertEqual(initial.gateway_result.classification.value, "CRITICAL")
        self.assertEqual(initial.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)

        self.assertTrue(delegated.executed)
        self.assertEqual(delegated.gateway_result.classification.value, "CRITICAL")
        self.assertEqual(delegated.gateway_result.decision, Decision.ALLOW)
        self.assertEqual(delegated.gateway_result.approval_method, "DELEGATION")
        self.assertEqual(delegated.exit_code, 0)
        self.assertTrue(len(delegated.stdout.strip()) > 0)

        self.assertFalse(exhausted.executed)
        self.assertEqual(exhausted.gateway_result.classification.value, "CRITICAL")
        self.assertEqual(exhausted.gateway_result.decision, Decision.DENY)
        self.assertIn("token exhausted", exhausted.reason)

        self.assertEqual(len(audit_entries), 3)
        self.assertEqual(
            [entry["decision"] for entry in audit_entries],
            ["REQUIRE_STRONG_APPROVAL", "ALLOW", "DENY"],
        )
        self.assertEqual(audit_entries[1]["approval_method"], "DELEGATION")
        self.assertIn("token exhausted", audit_entries[2]["reason"])


if __name__ == "__main__":
    unittest.main()
