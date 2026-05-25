from __future__ import annotations

import unittest

from agent_sudo.builders import AgentActionRequest
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import Classification, Decision
from agent_sudo.policy import load_default_policy


class PolicyPathRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_write_outside_allowed_absolute_path_blocked(self) -> None:
        request = AgentActionRequest.file_write("/home/user/example/outside.txt")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.classification, Classification.BLOCKED)
        self.assertEqual(result.decision, Decision.DENY)

    def test_write_inside_tmp_allowed_with_approval(self) -> None:
        request = AgentActionRequest.file_write("/tmp/agent-sudo-demo/notes.txt")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.classification, Classification.SENSITIVE)
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_ssh_path_write_blocked(self) -> None:
        request = AgentActionRequest.file_write("~/.ssh/config")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.classification, Classification.BLOCKED)
        self.assertEqual(result.decision, Decision.DENY)

    def test_config_path_write_blocked(self) -> None:
        request = AgentActionRequest.file_write("~/.config/agent/settings.json")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.classification, Classification.BLOCKED)
        self.assertEqual(result.decision, Decision.DENY)

    def test_policy_tampering_blocked(self) -> None:
        request = AgentActionRequest.file_edit("agent_sudo/config/default_policy.yaml")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(result.classification, Classification.BLOCKED)
        self.assertEqual(result.decision, Decision.DENY)


if __name__ == "__main__":
    unittest.main()
