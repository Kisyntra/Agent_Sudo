from __future__ import annotations

import unittest

from agent_sudo.builders import AgentActionRequest
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest, Classification, Decision
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

    def test_macos_store_reads_blocked(self) -> None:
        targets = [
            "~/Library/Keychains/login.keychain-db",
            "~/Library/Messages/chat.db",
            "~/Library/Mail/V10/MailData/Envelope Index",
            "~/Library/Cookies/Cookies.binarycookies",
            "~/Library/Safari/History.db",
            "~/Library/Application Support/Google/Chrome/Default/Cookies",
            "~/Library/Application Support/Google/Chrome/Default/Login Data",
            "~/Library/Application Support/Firefox/Profiles/example/Cookies.sqlite",
            "~/Library/Containers/com.apple.mail/Data/Mail/mailbox.db",
            "~/Library/Containers/com.apple.Notes/Data/Library/Notes/notes.db",
        ]

        for target in targets:
            with self.subTest(target=target):
                request = AgentActionRequest.file_read(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_macos_store_reads_are_case_insensitive(self) -> None:
        targets = [
            "~/library/keychains/login.keychain-db",
            "~/LIBRARY/MESSAGES/chat.db",
            "~/Library/safari/History.db",
            "~/Library/Application Support/Google/Chrome/Default/COOKIES",
        ]

        for target in targets:
            with self.subTest(target=target):
                request = AgentActionRequest.file_read(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_sensitive_search_paths_blocked(self) -> None:
        targets = [
            "~/.ssh",
            "~/.config/gcloud",
            "~/Library/Safari",
            "~/Library/Application Support/Google/Chrome/Default",
        ]

        for target in targets:
            with self.subTest(target=target):
                request = ActionRequest(
                    "codex",
                    "user",
                    "filesystem",
                    "search_files",
                    target,
                    "Search local files",
                    [],
                )
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_cookie_false_positives_are_not_blocked_outside_browser_profiles(
        self,
    ) -> None:
        safe_reads = [
            "docs/cookies-policy.md",
            "~/Library/Application Support/ExampleApp/Cookies",
        ]
        for target in safe_reads:
            with self.subTest(target=target):
                request = AgentActionRequest.file_read(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertNotEqual(result.classification, Classification.BLOCKED)
                self.assertNotEqual(result.decision, Decision.DENY)

    def test_extra_secret_file_reads_blocked(self) -> None:
        targets = [
            "~/.netrc",
            "~/.npmrc",
            "~/.pypirc",
            "~/.config/gcloud/application_default_credentials.json",
            "~/.kube/config",
        ]

        for target in targets:
            with self.subTest(target=target):
                request = AgentActionRequest.file_read(target)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_shell_sensitive_reads_blocked(self) -> None:
        commands = [
            "cat ~/Library/Keychains/login.keychain-db",
            "head ~/Library/Messages/chat.db",
            "grep token ~/.netrc",
            "less ~/.config/gcloud/application_default_credentials.json",
            "cp ~/.kube/config /tmp/kube-config-copy",
            "cat ~/Library/Safari/History.db",
            "cat ~/Library/Cookies/Cookies.binarycookies",
            "cat ~/Library/Application\\ Support/Google/Chrome/Default/Cookies",
        ]

        for command in commands:
            with self.subTest(command=command):
                request = AgentActionRequest.shell_command(command)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

    def test_shell_cookie_false_positive_not_blocked(self) -> None:
        request = AgentActionRequest.shell_command("cat docs/cookies-policy.md")
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertNotEqual(result.classification, Classification.BLOCKED)
        self.assertNotEqual(result.decision, Decision.DENY)

    def test_git_and_github_mutations_blocked_but_read_only_allowed(self) -> None:
        blocked_commands = [
            "gh release delete v0.5.1",
            "gh api -X DELETE /repos/example/project/releases/123",
            "gh api --method PATCH /repos/example/project/issues/1",
            "gh api /repos/example/project/issues -f title=bug",
            "gh api /repos/example/project/issues -F title=bug",
            "gh api /repos/example/project/issues --raw-field title=bug",
            "gh pr merge 41",
            "gh issue create --title bug --body body",
            "gh workflow run tests.yml",
            "gh run cancel 123",
            "git push origin main",
            "git -C /tmp/repo push origin main",
            "git -c credential.helper= push origin main",
            "git remote set-url origin git@example.invalid:repo.git",
            "git remote add mirror git@example.invalid:mirror.git",
        ]
        for command in blocked_commands:
            with self.subTest(command=command):
                request = AgentActionRequest.shell_command(command)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
                self.assertEqual(result.classification, Classification.BLOCKED)
                self.assertEqual(result.decision, Decision.DENY)

        allowed_commands = ["git status", "git log --oneline -1", "gh pr view 41"]
        for command in allowed_commands:
            with self.subTest(command=command):
                request = AgentActionRequest.shell_command(command)
                result = PermissionGateway(self.policy).evaluate(request, dry_run=True)
                self.assertEqual(result.classification, Classification.CRITICAL)
                self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)


if __name__ == "__main__":
    unittest.main()
