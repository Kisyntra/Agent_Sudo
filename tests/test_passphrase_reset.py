from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_sudo.approvals import (
    init_approval_config,
    hash_passphrase,
    verify_passphrase,
    load_approval_config,
)
from agent_sudo.delegations import DelegationStore
from agent_sudo.pending_approvals import PendingApprovalStore
from agent_sudo.audit import verify_audit_log
from agent_sudo.models import ActionRequest, ApprovalStatus, Decision, Classification
from agent_sudo.gateway import main


class PassphraseResetTests(unittest.TestCase):
    def test_first_run_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"

            # First-run setup: no existing config.
            prompts = []

            def mock_getpass(prompt):
                prompts.append(prompt)
                return "my-new-passphrase"

            init_approval_config(
                config_path=config_path,
                pending_approvals_path=Path(tmpdir) / "pending.json",
                delegations_path=Path(tmpdir) / "delegations.json",
                audit_log_path=Path(tmpdir) / "audit.jsonl",
                getpass_func=mock_getpass,
            )

            self.assertTrue(config_path.exists())
            config_data = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertIn("approval_hash", config_data)
            self.assertIn("approval_hash_salt", config_data)
            # Make sure raw passphrase is not stored anywhere
            self.assertNotIn(
                "my-new-passphrase", config_path.read_text(encoding="utf-8")
            )

            # Check correctness of hashing using verification helper
            self.assertTrue(verify_passphrase("my-new-passphrase", config_data))

    def test_existing_config_aborts_on_decline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            # Write an existing config
            initial_config = hash_passphrase("old-passphrase")
            config_path.write_text(json.dumps(initial_config), encoding="utf-8")

            delegations_path = Path(tmpdir) / "delegations.json"
            pending_path = Path(tmpdir) / "pending.json"
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Setup an active delegation and an active pending approval
            del_store = DelegationStore(delegations_path)
            del_store.create(
                actor="actor",
                allowed_actions=["read"],
                allowed_paths=["*"],
            )

            pending_store = PendingApprovalStore(pending_path)
            action_req = ActionRequest(
                actor="actor",
                source="test",
                tool="filesystem",
                action="read",
                target="file",
                payload_summary="summary",
            )
            pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="needed",
            )

            def mock_input(prompt):
                return "n"  # user declines

            # Should raise ValueError and not change anything
            with self.assertRaises(ValueError) as ctx:
                init_approval_config(
                    config_path=config_path,
                    delegations_path=delegations_path,
                    pending_approvals_path=pending_path,
                    audit_log_path=audit_path,
                    input_func=mock_input,
                )

            self.assertIn("aborted", str(ctx.exception))

            # Verify delegation, pending approval, and config are untouched
            tokens = del_store.list()
            self.assertEqual(len(tokens), 1)
            self.assertFalse(tokens[0].revoked)

            approvals = pending_store.list(update_expired=False)
            self.assertEqual(len(approvals), 1)
            self.assertEqual(approvals[0].status, ApprovalStatus.PENDING)

            self.assertEqual(load_approval_config(config_path), initial_config)
            self.assertFalse(audit_path.exists())

    def test_existing_config_resets_on_accept(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            initial_config = hash_passphrase("old-passphrase")
            config_path.write_text(json.dumps(initial_config), encoding="utf-8")

            delegations_path = Path(tmpdir) / "delegations.json"
            pending_path = Path(tmpdir) / "pending.json"
            audit_path = Path(tmpdir) / "audit.jsonl"

            # Setup active delegations, a PENDING and an APPROVED pending approvals,
            # plus historical records (USED, EXPIRED, DENIED).
            del_store = DelegationStore(delegations_path)
            # Active token
            del_store.create(actor="act", allowed_actions=["r"], allowed_paths=["*"])
            # Already revoked token
            tok_revoked = del_store.create(
                actor="act", allowed_actions=["w"], allowed_paths=["*"]
            )
            del_store.revoke(tok_revoked.token_id)

            pending_store = PendingApprovalStore(pending_path)
            action_req = ActionRequest(
                actor="actor",
                source="test",
                tool="filesystem",
                action="read",
                target="file",
                payload_summary="summary",
            )
            # Create PENDING approval
            pending_app = pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="pending",
            )
            # Create APPROVED approval
            approved_app = pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="approved",
            )
            # Manually simulate matching APPROVED status
            from dataclasses import replace

            approvals = pending_store.list(update_expired=False)
            updated = []
            for app in approvals:
                if app.approval_request_id == approved_app.approval_request_id:
                    app = replace(app, status=ApprovalStatus.APPROVED)
                updated.append(app)
            pending_store.save(updated)

            # Create USED, EXPIRED, DENIED approvals
            used_app = pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="used",
            )
            expired_app = pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="expired",
            )
            denied_app = pending_store.create(
                action_request=action_req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="denied",
            )

            approvals = pending_store.list(update_expired=False)
            updated = []
            for app in approvals:
                if app.approval_request_id == used_app.approval_request_id:
                    app = replace(app, status=ApprovalStatus.USED)
                elif app.approval_request_id == expired_app.approval_request_id:
                    app = replace(app, status=ApprovalStatus.EXPIRED)
                elif app.approval_request_id == denied_app.approval_request_id:
                    app = replace(app, status=ApprovalStatus.DENIED)
                updated.append(app)
            pending_store.save(updated)

            def mock_input(prompt):
                return "y"

            def mock_getpass(prompt):
                return "new-secure-passphrase"

            init_approval_config(
                config_path=config_path,
                delegations_path=delegations_path,
                pending_approvals_path=pending_path,
                audit_log_path=audit_path,
                getpass_func=mock_getpass,
                input_func=mock_input,
            )

            # Verify new config
            new_config = load_approval_config(config_path)
            self.assertNotEqual(initial_config, new_config)
            self.assertTrue(verify_passphrase("new-secure-passphrase", new_config))

            # Verify delegation revocation
            tokens = del_store.list()
            self.assertEqual(len(tokens), 2)
            for t in tokens:
                self.assertTrue(t.revoked)

            # Verify pending approvals cancellation
            approvals = pending_store.list(update_expired=False)
            self.assertEqual(len(approvals), 5)

            for app in approvals:
                if app.approval_request_id in {
                    pending_app.approval_request_id,
                    approved_app.approval_request_id,
                }:
                    # PENDING and APPROVED should be DENIED with passphrase reset reason
                    self.assertEqual(app.status, ApprovalStatus.DENIED)
                    self.assertEqual(app.reason, "passphrase was reset")
                elif app.approval_request_id == used_app.approval_request_id:
                    self.assertEqual(app.status, ApprovalStatus.USED)
                elif app.approval_request_id == expired_app.approval_request_id:
                    self.assertEqual(app.status, ApprovalStatus.EXPIRED)
                elif app.approval_request_id == denied_app.approval_request_id:
                    self.assertEqual(app.status, ApprovalStatus.DENIED)
                    self.assertEqual(app.reason, "denied")  # unchanged

            # Verify audit event and hash chain validity
            self.assertTrue(audit_path.exists())
            ok, msg = verify_audit_log(audit_path)
            self.assertTrue(ok, msg)

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            last_entry = json.loads(lines[-1])
            self.assertEqual(last_entry["event_type"], "passphrase_reset")
            self.assertEqual(last_entry["revoked_delegations_count"], 1)
            self.assertEqual(last_entry["canceled_pending_approvals_count"], 2)
            self.assertEqual(
                last_entry["config_path_redacted"], "~/.agent-sudo/config.json"
            )
            self.assertIn("timestamp", last_entry)

    def test_force_flag_bypasses_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            initial_config = hash_passphrase("old-passphrase")
            config_path.write_text(json.dumps(initial_config), encoding="utf-8")

            delegations_path = Path(tmpdir) / "delegations.json"
            pending_path = Path(tmpdir) / "pending.json"
            audit_path = Path(tmpdir) / "audit.jsonl"

            del_store = DelegationStore(delegations_path)
            del_store.create(actor="act", allowed_actions=["r"], allowed_paths=["*"])

            def mock_getpass(prompt):
                return "forced-passphrase"

            init_approval_config(
                config_path=config_path,
                delegations_path=delegations_path,
                pending_approvals_path=pending_path,
                audit_log_path=audit_path,
                force=True,
                getpass_func=mock_getpass,
                input_func=lambda p: self.fail(
                    "input_func should not be called when force is True"
                ),
            )

            new_config = load_approval_config(config_path)
            self.assertTrue(verify_passphrase("forced-passphrase", new_config))
            self.assertTrue(del_store.list()[0].revoked)

            lines = audit_path.read_text(encoding="utf-8").splitlines()
            last_entry = json.loads(lines[-1])
            self.assertEqual(last_entry["event_type"], "passphrase_reset")
            self.assertEqual(last_entry["revoked_delegations_count"], 1)

    def test_cli_integration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.json"
            initial_config = hash_passphrase("old-passphrase")
            config_path.write_text(json.dumps(initial_config), encoding="utf-8")

            pending_path = Path(tmpdir) / "pending.json"
            delegations_path = Path(tmpdir) / "delegations.json"
            audit_path = Path(tmpdir) / "audit.jsonl"

            del_store = DelegationStore(delegations_path)
            del_store.create(actor="act", allowed_actions=["r"], allowed_paths=["*"])

            with (
                patch(
                    "agent_sudo.approvals.getpass.getpass",
                    return_value="cli-passphrase",
                ),
                patch("builtins.input", return_value="y"),
            ):
                argv = [
                    "init-approval",
                    "--config",
                    str(config_path),
                    "--pending-approvals-file",
                    str(pending_path),
                    "--delegations-file",
                    str(delegations_path),
                    "--audit-log",
                    str(audit_path),
                ]
                code = main(argv)
                self.assertEqual(code, 0)

            new_config = load_approval_config(config_path)
            self.assertTrue(verify_passphrase("cli-passphrase", new_config))
            self.assertTrue(del_store.list()[0].revoked)
