from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.builders import AgentActionRequest
from agent_sudo.delegations import DelegationStore
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import ActionRequest, ApprovalResult, Decision
from agent_sudo.policy import load_default_policy


class NoTtyApprovalProvider(ApprovalProvider):
    def __init__(self) -> None:
        super().__init__(stdin_is_tty=lambda: False)


class ApproveCriticalProvider(ApprovalProvider):
    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(True, "PASSPHRASE_CONFIRM", "approved")


class DelegationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def _store(self, tmpdir: str) -> DelegationStore:
        return DelegationStore(Path(tmpdir) / "delegations.json")

    def test_valid_delegation_allows_matching_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="agent-a",
                allowed_actions=["read_file"],
                allowed_paths=["/home/user/example/project"],
                ttl_seconds=7200,
                max_uses=5,
                reason="project files",
            )
            request = AgentActionRequest.file_read(
                "/home/user/example/project/README.md",
                actor="agent-a",
                source="unknown",
                source_trust="UNKNOWN",
            )
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(request)

        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertEqual(result.approval_method, "DELEGATION")

    def test_expired_token_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="agent-a",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                ttl_seconds=-1,
                max_uses=5,
                reason="expired",
            )
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                AgentActionRequest.file_edit("README.md", actor="agent-a")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.reason, "delegation token is expired")

    def test_revoked_token_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
                actor="hermes",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="revoked",
            )
            store.revoke(token.token_id)
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                AgentActionRequest.file_edit("README.md", actor="hermes")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.reason, "delegation token is revoked")

    def test_path_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="readme only",
            )
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                AgentActionRequest.file_edit("docs/other.md", actor="codex")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.reason, "delegation scope mismatch")

    def test_actor_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="hermes",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="hermes only",
            )
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                AgentActionRequest.file_edit("README.md", actor="codex")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertEqual(result.reason, "delegation scope mismatch")

    def test_max_uses_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=1,
                reason="once",
            )
            gateway = PermissionGateway(self.policy, delegation_store=store)
            first = gateway.evaluate(AgentActionRequest.file_edit("README.md", actor="codex"))
            second = gateway.evaluate(AgentActionRequest.file_edit("README.md", actor="codex"))

        self.assertEqual(first.decision, Decision.ALLOW)
        self.assertEqual(second.decision, Decision.DENY)
        self.assertEqual(second.reason, "delegation token is exhausted")

    def test_critical_actions_require_strong_approval_unless_delegated_critical_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["send_email"],
                allowed_paths=["recipient@example.invalid"],
                max_uses=5,
                reason="not critical",
                critical=False,
            )
            result = PermissionGateway(
                self.policy,
                approvals=NoTtyApprovalProvider(),
                delegation_store=store,
            ).evaluate(AgentActionRequest.send_email("recipient@example.invalid", actor="codex"))

            critical_store = self._store(str(Path(tmpdir) / "critical"))
            critical_store.create(
                actor="codex",
                allowed_actions=["send_email"],
                allowed_paths=["recipient@example.invalid"],
                max_uses=5,
                reason="email approved",
                critical=True,
            )
            delegated = PermissionGateway(self.policy, delegation_store=critical_store).evaluate(
                AgentActionRequest.send_email("recipient@example.invalid", actor="codex")
            )

        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertEqual(delegated.decision, Decision.ALLOW)
        self.assertEqual(delegated.approval_method, "DELEGATION")

    def test_delegate_cli_create_list_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "delegations.json"
            with redirect_stdout(StringIO()):
                create_code = main(
                    [
                        "delegate",
                        "create",
                        "--actor",
                        "codex",
                        "--allow-action",
                        "edit_file",
                        "--allow-path",
                        "README.md",
                        "--max-uses",
                        "2",
                        "--reason",
                        "docs",
                        "--delegations-file",
                        str(path),
                    ]
                )
                tokens = self._store(tmpdir).list()
                list_code = main(["delegate", "list", "--delegations-file", str(path)])
                revoke_code = main(["delegate", "revoke", tokens[0].token_id, "--delegations-file", str(path)])
            revoked = self._store(tmpdir).list()[0]

        self.assertEqual(create_code, 0)
        self.assertEqual(list_code, 0)
        self.assertEqual(revoke_code, 0)
        self.assertTrue(revoked.revoked)


if __name__ == "__main__":
    unittest.main()
