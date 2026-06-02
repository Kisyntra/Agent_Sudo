from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.builders import AgentActionRequest
from agent_sudo.delegations import (
    DELEGATIONS_PATH,
    DELEGATIONS_PATH_ENV,
    DelegationStore,
    default_delegations_path,
)
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
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                request
            )

        self.assertEqual(result.decision, Decision.ALLOW)
        self.assertEqual(result.approval_method, "DELEGATION")

    def test_expired_token_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
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
        self.assertIn("token expired", result.reason)
        self.assertIn(token.token_id, result.reason)

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
        self.assertIn("token revoked", result.reason)
        self.assertIn(token.token_id, result.reason)

    def test_path_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
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
        self.assertIn("path mismatch", result.reason)
        self.assertIn("expected path scope in ['README.md']", result.reason)
        self.assertIn("actual target 'docs/other.md'", result.reason)
        self.assertIn(token.token_id, result.reason)

    def test_actor_mismatch_denied(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
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
        self.assertIn("actor mismatch", result.reason)
        self.assertIn("expected actor 'hermes'", result.reason)
        self.assertIn("actual actor 'codex'", result.reason)
        self.assertIn(token.token_id, result.reason)

    def test_max_uses_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
                actor="codex",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=1,
                reason="once",
            )
            gateway = PermissionGateway(self.policy, delegation_store=store)
            first = gateway.evaluate(
                AgentActionRequest.file_edit("README.md", actor="codex")
            )
            second = gateway.evaluate(
                AgentActionRequest.file_edit("README.md", actor="codex")
            )

        self.assertEqual(first.decision, Decision.ALLOW)
        self.assertEqual(second.decision, Decision.DENY)
        self.assertIn("token exhausted", second.reason)
        self.assertIn(token.token_id, second.reason)

    def test_action_mismatch_explains_action_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
                actor="hermes",
                allowed_actions=["read_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="read only",
            )
            result = PermissionGateway(self.policy, delegation_store=store).evaluate(
                AgentActionRequest.file_edit("README.md", actor="hermes")
            )

        self.assertEqual(result.decision, Decision.DENY)
        self.assertIn("action mismatch", result.reason)
        self.assertIn("expected action in ['read_file']", result.reason)
        self.assertIn("actual action 'edit_file'", result.reason)
        self.assertIn(token.token_id, result.reason)

    def test_critical_flag_missing_explains_critical_flag_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            token = store.create(
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
            ).evaluate(
                AgentActionRequest.send_email(
                    "recipient@example.invalid", actor="codex"
                )
            )

        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertIn("critical flag missing", result.reason)
        self.assertIn(token.token_id, result.reason)

    def test_critical_actions_require_strong_approval_unless_delegated_critical_true(
        self,
    ) -> None:
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
            ).evaluate(
                AgentActionRequest.send_email(
                    "recipient@example.invalid", actor="codex"
                )
            )

            critical_store = self._store(str(Path(tmpdir) / "critical"))
            critical_store.create(
                actor="codex",
                allowed_actions=["send_email"],
                allowed_paths=["recipient@example.invalid"],
                max_uses=5,
                reason="email approved",
                critical=True,
            )
            delegated = PermissionGateway(
                self.policy, delegation_store=critical_store
            ).evaluate(
                AgentActionRequest.send_email(
                    "recipient@example.invalid", actor="codex"
                )
            )

        self.assertEqual(result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertEqual(delegated.decision, Decision.ALLOW)
        self.assertEqual(delegated.approval_method, "DELEGATION")

    def test_delegate_cli_create_list_revoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "delegations.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
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
                revoke_code = main(
                    [
                        "delegate",
                        "revoke",
                        tokens[0].token_id,
                        "--delegations-file",
                        str(path),
                    ]
                )
            revoked = self._store(tmpdir).list()[0]

        self.assertEqual(create_code, 0)
        self.assertEqual(list_code, 0)
        self.assertEqual(revoke_code, 0)
        self.assertTrue(revoked.revoked)

    def test_delegate_cli_create_reports_explicit_delegations_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "delegations.json"
            stdout = StringIO()
            stderr = StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
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
                        "--delegations-file",
                        str(path),
                    ]
                )

        token = json.loads(stdout.getvalue())
        self.assertEqual(create_code, 0)
        self.assertEqual(token["actor"], "codex")
        self.assertIn(f"delegations file: {path}", stderr.getvalue())
        self.assertNotIn("warning: using default delegation store", stderr.getvalue())

    def test_delegate_cli_create_warns_for_default_delegations_file(self) -> None:
        class FakeToken:
            def to_dict(self) -> dict[str, object]:
                return {
                    "actor": "codex",
                    "allowed_actions": ["edit_file"],
                    "allowed_paths": ["README.md"],
                    "token_id": "test-token",
                }

        class FakeStore:
            path = DELEGATIONS_PATH

            def create(self, **kwargs: object) -> FakeToken:
                return FakeToken()

        stdout = StringIO()
        stderr = StringIO()
        with patch.dict(os.environ):
            os.environ.pop(DELEGATIONS_PATH_ENV, None)
            with patch("agent_sudo.gateway.DelegationStore", return_value=FakeStore()):
                with redirect_stdout(stdout), redirect_stderr(stderr):
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
                        ]
                    )

        token = json.loads(stdout.getvalue())
        self.assertEqual(create_code, 0)
        self.assertEqual(token["actor"], "codex")
        self.assertIn(f"delegations file: {DELEGATIONS_PATH}", stderr.getvalue())
        self.assertIn("warning: using default delegation store", stderr.getvalue())
        self.assertIn(str(DELEGATIONS_PATH), stderr.getvalue())


class DelegationStorePathResolutionTests(unittest.TestCase):
    """Resolution of the default delegation store path (env-aware, use-time)."""

    def test_default_used_when_env_unset(self) -> None:
        with patch.dict(os.environ):
            os.environ.pop(DELEGATIONS_PATH_ENV, None)
            self.assertEqual(default_delegations_path(), DELEGATIONS_PATH)
            self.assertEqual(DelegationStore().path, DELEGATIONS_PATH)

    def test_env_var_sets_default(self) -> None:
        with patch.dict(
            os.environ, {DELEGATIONS_PATH_ENV: "/tmp/hermes/delegations.json"}
        ):
            self.assertEqual(
                DelegationStore().path, Path("/tmp/hermes/delegations.json")
            )

    def test_env_var_expands_user(self) -> None:
        with patch.dict(
            os.environ, {DELEGATIONS_PATH_ENV: "~/.hermes/delegations.json"}
        ):
            resolved = DelegationStore().path
            self.assertEqual(resolved, Path.home() / ".hermes" / "delegations.json")
            self.assertNotIn("~", str(resolved))

    def test_explicit_path_overrides_env(self) -> None:
        with patch.dict(
            os.environ, {DELEGATIONS_PATH_ENV: "/tmp/hermes/delegations.json"}
        ):
            explicit = Path("/tmp/explicit/delegations.json")
            self.assertEqual(DelegationStore(explicit).path, explicit)

    def test_resolution_is_use_time_not_import_time(self) -> None:
        # A store constructed after the env changes must observe the new value,
        # proving resolution happens when DelegationStore() is created.
        with patch.dict(os.environ):
            os.environ.pop(DELEGATIONS_PATH_ENV, None)
            self.assertEqual(DelegationStore().path, DELEGATIONS_PATH)
            os.environ[DELEGATIONS_PATH_ENV] = "/tmp/late/delegations.json"
            self.assertEqual(DelegationStore().path, Path("/tmp/late/delegations.json"))

    def test_cli_create_uses_env_default_without_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "delegations.json"
            stdout = StringIO()
            stderr = StringIO()
            with patch.dict(os.environ, {DELEGATIONS_PATH_ENV: str(store_path)}):
                with redirect_stdout(stdout), redirect_stderr(stderr):
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
                        ]
                    )

            self.assertEqual(create_code, 0)
            # Token landed in the env store, no --delegations-file needed.
            self.assertTrue(store_path.exists())
            self.assertIn(f"delegations file: {store_path}", stderr.getvalue())
            # The default-store footgun warning must NOT fire when env is set.
            self.assertNotIn(
                "warning: using default delegation store", stderr.getvalue()
            )


if __name__ == "__main__":
    unittest.main()
