from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_sudo.audit import AuditLogger, verify_audit_log
from agent_sudo.builders import AgentActionRequest
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest, Classification, Decision
from agent_sudo.policy import load_default_policy


class TamperResistanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_editing_policy_requires_strong_approval(self) -> None:
        request = AgentActionRequest.file_edit("agent_sudo/config/default_policy.yaml")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.decision, Decision.DENY)

    def test_deleting_audit_log_is_denied_or_critical(self) -> None:
        request = AgentActionRequest.file_delete("~/.agent-sudo/audit.jsonl")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertIn(
            result.decision, {Decision.DENY, Decision.REQUIRE_STRONG_APPROVAL}
        )

    def test_modifying_auth_file_requires_strong_approval(self) -> None:
        request = AgentActionRequest.file_edit("~/.agent-runtime/auth.json")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.decision, Decision.DENY)

    def test_direct_modify_auth_action_is_blocked(self) -> None:
        request = AgentActionRequest.modify_auth("~/.agent-runtime/auth.json")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.decision, Decision.DENY)

    def test_normal_readme_edit_remains_sensitive(self) -> None:
        request = AgentActionRequest.file_edit("README.md")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_agent_sudo_source_edit_requires_strong_approval(self) -> None:
        request = AgentActionRequest.file_edit("agent_sudo/gateway.py")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_specific_tamper_actions_are_blocked(self) -> None:
        for action in [
            "disable_audit",
            "modify_policy_without_approval",
            "delete_audit_log",
            "edit_agent_sudo_source",
            "modify_auth",
        ]:
            with self.subTest(action=action):
                request = ActionRequest(
                    "codex",
                    "webpage",
                    "tamper",
                    action,
                    "agent_sudo/config/default_policy.yaml",
                    "tamper",
                )
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
                self.assertEqual(result.decision, Decision.DENY)

    def test_audit_hash_chain_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            gateway = PermissionGateway(
                self.policy, audit_logger=AuditLogger(audit_path)
            )
            gateway.evaluate(AgentActionRequest.file_read("README.md"))
            gateway.evaluate(AgentActionRequest.file_edit("README.md"), dry_run=True)

            ok, message = verify_audit_log(audit_path)

        self.assertTrue(ok, message)

    def test_tampered_audit_log_fails_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            gateway = PermissionGateway(
                self.policy, audit_logger=AuditLogger(audit_path)
            )
            gateway.evaluate(AgentActionRequest.file_read("README.md"))

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            entry = json.loads(lines[0])
            entry["decision"] = "DENY"
            audit_path.write_text(
                json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8"
            )

            ok, message = verify_audit_log(audit_path)

        self.assertFalse(ok)
        self.assertIn("entry_hash mismatch", message)

    def test_shell_command_tamper_bypasses_are_blocked(self) -> None:
        bypass_commands = [
            'echo "safe: [run_shell_command]" > ~/.agent-sudo/policy.yaml',
            'echo "rules: []" > ~/.agent-sudo/policy.yaml && echo 1',
            "mv /tmp/payload.yaml ~/.agent-sudo/policy.yaml",
            "cp /tmp/payload.yaml ~/.agent-sudo/policy.yaml",
            "ln -sf /tmp/payload.yaml ~/.agent-sudo/policy.yaml",
            "rsync /tmp/payload.yaml ~/.agent-sudo/policy.yaml",
            "tar -xf /tmp/archive.tar -C ~/.agent-sudo/",
            "cat ~/.agent-sudo/policy.yaml",
            'bash -c "echo hack > ~/.agent-sudo/policy.yaml"',
            'echo "safe: [run_shell_command]" > $HOME/.agent-sudo/policy.yaml',
            'echo "safe: [run_shell_command]" > ~/.config/../.agent-sudo/policy.yaml',
            'echo "safe: [run_shell_command]" > ../.agent-sudo/policy.yaml',
            'cat "~/.agent-sudo/policy.yaml"',
            "echo x>~/.agent-sudo/policy.yaml",
            "tee ~/.agent-sudo/policy.yaml",
            "dd of=~/.agent-sudo/policy.yaml",
            "tar -xf payload.tar -C ~/.agent-sudo/",
        ]
        for cmd in bypass_commands:
            with self.subTest(command=cmd):
                request = AgentActionRequest.shell_command(cmd)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_shell_command_symlink_bypass_is_blocked(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            fake_agent_sudo = Path(tmpdir) / ".agent-sudo"
            fake_agent_sudo.mkdir()
            fake_policy = fake_agent_sudo / "policy.yaml"
            fake_policy.write_text("rules: []", encoding="utf-8")

            symlink_path = Path(tmpdir) / "mysymlink"
            os.symlink(str(fake_policy), str(symlink_path))

            cmd = f"echo 'hacked' > {symlink_path}"
            request = AgentActionRequest.shell_command(cmd)
            result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
            self.assertEqual(result.classification, Classification.BLOCKED)
            self.assertEqual(result.decision, Decision.DENY)


if __name__ == "__main__":
    unittest.main()
