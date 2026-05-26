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

    def test_relative_executable_write_is_critical(self) -> None:
        critical_targets = [
            "scripts/deploy.sh",
            "scripts/bootstrap.bash",
            "scripts/start.zsh",
            "tools/release.py",
            "web/build.js",
            "web/build.ts",
            "tools/task.rb",
            "tools/task.pl",
        ]

        for target in critical_targets:
            with self.subTest(target=target):
                request = AgentActionRequest.file_write(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.CRITICAL)
                self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_shell_rc_write_is_critical(self) -> None:
        for target in ["~/.zshrc", "~/.bashrc"]:
            with self.subTest(target=target):
                request = AgentActionRequest.file_write(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.CRITICAL)
                self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_runtime_control_files_are_critical(self) -> None:
        critical_targets = [
            "~/Library/LaunchAgents/com.example.agent.plist",
            "/etc/cron.d/agent-sudo",
            "/etc/systemd/system/agent-sudo.service",
            "~/.config/mcp/settings.json",
            "~/.agent-runtime/config.toml",
        ]

        for target in critical_targets:
            with self.subTest(target=target):
                request = AgentActionRequest.file_edit(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.CRITICAL)
                self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)

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

    def test_protected_reads(self) -> None:
        # README.md => SAFE
        req_readme = AgentActionRequest.file_read("README.md")
        res_readme = PermissionGateway(self.policy).evaluate(req_readme, dry_run=True)
        self.assertEqual(res_readme.classification, Classification.SAFE)
        self.assertEqual(res_readme.decision, Decision.ALLOW)

        # ~/.ssh/config => BLOCKED
        req_ssh = AgentActionRequest.file_read("~/.ssh/config")
        res_ssh = PermissionGateway(self.policy).evaluate(req_ssh, dry_run=True)
        self.assertEqual(res_ssh.classification, Classification.BLOCKED)
        self.assertEqual(res_ssh.decision, Decision.DENY)

        # .env => BLOCKED
        req_env = AgentActionRequest.file_read(".env")
        res_env = PermissionGateway(self.policy).evaluate(req_env, dry_run=True)
        self.assertEqual(res_env.classification, Classification.BLOCKED)
        self.assertEqual(res_env.decision, Decision.DENY)

        # auth.json => BLOCKED
        req_auth = AgentActionRequest.file_read("auth.json")
        res_auth = PermissionGateway(self.policy).evaluate(req_auth, dry_run=True)
        self.assertEqual(res_auth.classification, Classification.BLOCKED)
        self.assertEqual(res_auth.decision, Decision.DENY)

        # token_store.json => BLOCKED
        req_token = AgentActionRequest.file_read("token_store.json")
        res_token = PermissionGateway(self.policy).evaluate(req_token, dry_run=True)
        self.assertEqual(res_token.classification, Classification.BLOCKED)
        self.assertEqual(res_token.decision, Decision.DENY)


if __name__ == "__main__":
    unittest.main()
