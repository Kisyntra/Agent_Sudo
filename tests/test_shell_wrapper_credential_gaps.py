"""Regression tests for issue #49.

Two classifier hard-DENY gaps in shell commands:

1. Wrapper-prefixed destructive ``rm`` (``sudo``/``env``/``command``/``time``/
   ``nice``/``nohup``/``timeout`` ...) shifted ``rm`` off argv[0] and fell
   through to ``REQUIRE_STRONG_APPROVAL`` instead of hard ``DENY``.
2. Shell reads of ``~/.aws/credentials`` were not treated as credential paths,
   so they diverged from ``read_file`` handling of the same file.

Goal: ``rm -rf /`` and ``sudo rm -rf /`` land in the same policy outcome, and
credential files are treated consistently across shell reads and ``read_file``.
"""

from __future__ import annotations

import unittest

from agent_sudo.builders import AgentActionRequest
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import Classification, Decision
from agent_sudo.policy import load_default_policy


class ShellWrapperCredentialGapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = PermissionGateway(load_default_policy())

    def _shell(self, command: str):
        return self.gateway.evaluate(
            AgentActionRequest.shell_command(command), dry_run=True
        )

    def _assert_blocked(self, command: str) -> None:
        result = self._shell(command)
        self.assertEqual(result.classification, Classification.BLOCKED, msg=command)
        self.assertEqual(result.decision, Decision.DENY, msg=command)

    def test_bare_and_sudo_rm_share_outcome(self) -> None:
        bare = self._shell("rm -rf /")
        sudo = self._shell("sudo rm -rf /")
        self.assertEqual(bare.decision, Decision.DENY)
        self.assertEqual(sudo.decision, bare.decision)
        self.assertEqual(sudo.classification, bare.classification)

    def test_wrapper_prefixed_destructive_rm_blocked(self) -> None:
        for command in [
            "sudo rm -rf /",
            "env rm -rf /",
            "command rm -rf /",
            "time rm -rf /",
            "nice rm -rf /",
            "nohup rm -rf /",
            "timeout 5 rm -rf /",
            "sudo -u root rm -rf /",
            "sudo env rm -rf /",
        ]:
            with self.subTest(command=command):
                self._assert_blocked(command)

    def test_aws_credentials_shell_read_blocked(self) -> None:
        self._assert_blocked("cat ~/.aws/credentials")

    def test_other_credential_paths_blocked(self) -> None:
        for command in [
            "cat ~/.config/gcloud/application_default_credentials.json",
            "cat ~/.kube/config",
            "cat ~/.ssh/id_rsa",
        ]:
            with self.subTest(command=command):
                self._assert_blocked(command)

    def test_shell_and_read_file_credential_consistency(self) -> None:
        shell = self._shell("cat ~/.aws/credentials")
        read = self.gateway.evaluate(
            AgentActionRequest.file_read("~/.aws/credentials"), dry_run=True
        )
        self.assertEqual(shell.decision, Decision.DENY)
        self.assertEqual(shell.decision, read.decision)
        self.assertEqual(shell.classification, read.classification)

    def test_benign_commands_not_newly_blocked(self) -> None:
        # These must not be hard-denied by the #49 changes; they keep their
        # prior (non-DENY) classification.
        for command in [
            "rm file.txt",
            "ls -la",
            "grep credentials src/app.py",
            "python secrets_manager.py",
            "cat README.md",
        ]:
            with self.subTest(command=command):
                self.assertNotEqual(self._shell(command).decision, Decision.DENY)


if __name__ == "__main__":
    unittest.main()
