from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
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
    delegation_status,
    is_broad_delegation,
)
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import (
    ActionRequest,
    ApprovalResult,
    Classification,
    Decision,
    DelegationToken,
)
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

    def test_path_mismatch_does_not_block_approval(self) -> None:
        # A token scoped to a different path is unrelated to this request: it must
        # not convert an approval-required action into a hard DENY (issue #77).
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="readme only",
            )
            result = PermissionGateway(
                self.policy,
                approvals=NoTtyApprovalProvider(),
                delegation_store=store,
            ).evaluate(AgentActionRequest.file_edit("docs/other.md", actor="codex"))

        self.assertNotEqual(result.decision, Decision.DENY)
        self.assertIn(
            result.decision,
            {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL},
        )
        self.assertNotEqual(result.approval_method, "DELEGATION")

    def test_actor_mismatch_does_not_block_approval(self) -> None:
        # A token for a different actor is unrelated: it must not deny this actor's
        # request, only fail to grant it (issue #77).
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="hermes",
                allowed_actions=["edit_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="hermes only",
            )
            result = PermissionGateway(
                self.policy,
                approvals=NoTtyApprovalProvider(),
                delegation_store=store,
            ).evaluate(AgentActionRequest.file_edit("README.md", actor="codex"))

        self.assertNotEqual(result.decision, Decision.DENY)
        self.assertIn(
            result.decision,
            {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL},
        )
        self.assertNotEqual(result.approval_method, "DELEGATION")

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

    def test_action_mismatch_does_not_block_approval(self) -> None:
        # A token granting a different action is unrelated to this request: it must
        # not deny, only fail to grant (issue #77).
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="hermes",
                allowed_actions=["read_file"],
                allowed_paths=["README.md"],
                max_uses=5,
                reason="read only",
            )
            result = PermissionGateway(
                self.policy,
                approvals=NoTtyApprovalProvider(),
                delegation_store=store,
            ).evaluate(AgentActionRequest.file_edit("README.md", actor="hermes"))

        self.assertNotEqual(result.decision, Decision.DENY)
        self.assertIn(
            result.decision,
            {Decision.REQUIRE_APPROVAL, Decision.REQUIRE_STRONG_APPROVAL},
        )
        self.assertNotEqual(result.approval_method, "DELEGATION")

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


class DelegationApprovalReachabilityTests(unittest.TestCase):
    """Issue #77: unrelated/expired/mismatched tokens must not turn an
    approval-required action into a hard DENY. authorize() returns:
      True  → an applicable, usable token grants the action
      False → an explicit denial, or a relevant grant that is unusable
      None  → no token applies; fall through to the normal approval path
    """

    def _store(self, tmpdir: str) -> DelegationStore:
        return DelegationStore(Path(tmpdir) / "delegations.json")

    def _authorize(self, store: DelegationStore, request: ActionRequest):
        return store.authorize(
            request, classification=Classification.SENSITIVE, consume=False
        )

    def test_unrelated_expired_token_does_not_block_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="hermes",
                allowed_actions=["read_file"],
                allowed_paths=["/other/scope"],
                ttl_seconds=-1,  # expired
                max_uses=5,
                reason="stale unrelated",
            )
            result, reason, method = self._authorize(
                store,
                AgentActionRequest.file_read("/my/file.txt", actor="codex"),
            )
        self.assertIsNone(result)
        self.assertEqual(method, "none")
        self.assertEqual(reason, "no delegation matched")

    def test_mismatched_token_does_not_block_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["read_file"],
                allowed_paths=["/my/file.txt"],
                max_uses=5,
                reason="read only, active",
            )
            # Same actor + path, different action → not relevant → approval path.
            result, _reason, method = self._authorize(
                store,
                AgentActionRequest.file_edit("/my/file.txt", actor="codex"),
            )
        self.assertIsNone(result)
        self.assertEqual(method, "none")

    def test_explicit_denied_action_still_denies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=[],
                denied_actions=["run_shell_command"],
                allowed_paths=["*"],
                max_uses=5,
                reason="explicit deny",
            )
            result, reason, method = self._authorize(
                store,
                AgentActionRequest.shell_command("pwd", actor="codex"),
            )
        self.assertIs(result, False)
        self.assertEqual(method, "DELEGATION")
        self.assertIn("explicitly denies", reason)

    def test_valid_matching_delegation_still_allows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["read_file"],
                allowed_paths=["/my/file.txt"],
                max_uses=5,
                reason="valid",
            )
            result, _reason, method = self._authorize(
                store,
                AgentActionRequest.file_read("/my/file.txt", actor="codex"),
            )
        self.assertIs(result, True)
        self.assertEqual(method, "DELEGATION")

    def test_exhausted_matching_token_still_denies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="codex",
                allowed_actions=["read_file"],
                allowed_paths=["/my/file.txt"],
                max_uses=1,
                reason="one use",
            )
            request = AgentActionRequest.file_read("/my/file.txt", actor="codex")
            # Consume the single use, then it is a relevant-but-exhausted grant.
            first = store.authorize(
                request, classification=Classification.SENSITIVE, consume=True
            )
            second = store.authorize(
                request, classification=Classification.SENSITIVE, consume=True
            )
        self.assertIs(first[0], True)
        self.assertIs(second[0], False)
        self.assertIn("token exhausted", second[1])

    def test_only_stale_unrelated_tokens_defer_to_approval(self) -> None:
        # The Antigravity dogfood scenario: several stale, unrelated tokens in the
        # store and a request none of them apply to → approval stays reachable.
        with tempfile.TemporaryDirectory() as tmpdir:
            store = self._store(tmpdir)
            store.create(
                actor="hermes",
                allowed_actions=["run_shell_command"],
                allowed_paths=["ls"],
                ttl_seconds=-1,
                max_uses=1,
                reason="stale 1",
            )
            store.create(
                actor="old-agent",
                allowed_actions=["write_file"],
                allowed_paths=["/tmp/x"],
                max_uses=0,  # exhausted
                reason="stale 2",
            )
            result, reason, method = self._authorize(
                store,
                AgentActionRequest.shell_command("pwd", actor="codex"),
            )
        self.assertIsNone(result)
        self.assertEqual(method, "none")
        self.assertEqual(reason, "no delegation matched")


class DelegationObservabilityTests(unittest.TestCase):
    """Display-only helpers behind `delegate list` / `doctor`. These describe a
    token; they do not affect authorization."""

    FIXED_NOW = datetime(2026, 6, 6, 3, 0, 0, tzinfo=timezone.utc)

    def _token(self, **overrides) -> DelegationToken:
        data = {
            "token_id": "t",
            "actor": "mcp-client",
            "allowed_actions": ["write_file"],
            "allowed_paths": ["/ws/a.txt"],
            "denied_actions": [],
            "expires_at": "2026-06-06T05:00:00Z",  # future relative to FIXED_NOW
            "max_uses": 5,
            "uses": 0,
            "revoked": False,
            "critical": False,
            "created_at": "2026-06-06T01:00:00Z",
        }
        data.update(overrides)
        return DelegationToken.from_dict(data)

    def test_status_active(self) -> None:
        token = self._token()
        self.assertEqual(delegation_status(token, self.FIXED_NOW), "active")

    def test_status_revoked(self) -> None:
        token = self._token(revoked=True)
        self.assertEqual(delegation_status(token, self.FIXED_NOW), "revoked")

    def test_status_expired(self) -> None:
        token = self._token(expires_at="2026-06-06T02:00:00Z")  # past
        self.assertEqual(delegation_status(token, self.FIXED_NOW), "expired")

    def test_status_exhausted(self) -> None:
        token = self._token(max_uses=3, uses=3)
        self.assertEqual(delegation_status(token, self.FIXED_NOW), "exhausted")

    def test_status_combination_revoked_and_expired(self) -> None:
        token = self._token(revoked=True, expires_at="2026-06-06T02:00:00Z")
        self.assertEqual(delegation_status(token, self.FIXED_NOW), "revoked, expired")

    def test_broad_wildcard_path(self) -> None:
        self.assertTrue(is_broad_delegation(self._token(allowed_paths=["*"])))

    def test_broad_empty_path(self) -> None:
        self.assertTrue(is_broad_delegation(self._token(allowed_paths=[])))

    def test_narrow_path_not_broad(self) -> None:
        self.assertFalse(is_broad_delegation(self._token(allowed_paths=["/ws/a.txt"])))

    def test_delegate_list_surfaces_status_and_broad(self) -> None:
        # End-to-end through the CLI: enriched fields appear in the output and
        # the stored token shape is unchanged on disk.
        with tempfile.TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "delegations.json"
            store = DelegationStore(store_path)
            store.save([self._token(token_id="broad", allowed_paths=["*"])])

            out = StringIO()
            with redirect_stdout(out):
                code = main(["delegate", "list", "--delegations-file", str(store_path)])
            self.assertEqual(code, 0)
            rows = json.loads(out.getvalue())
            self.assertEqual(len(rows), 1)
            self.assertIn("status", rows[0])
            self.assertEqual(rows[0]["broad"], True)
            # Persisted file must not gain the derived fields.
            on_disk = json.loads(store_path.read_text(encoding="utf-8"))
            self.assertNotIn("status", on_disk[0])
            self.assertNotIn("broad", on_disk[0])


if __name__ == "__main__":
    unittest.main()
