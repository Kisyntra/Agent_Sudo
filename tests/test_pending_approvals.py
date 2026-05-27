from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from agent_sudo.approvals import ApprovalProvider, hash_passphrase
from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.mcp_server import build_server
from agent_sudo.mcp_gateway import dispatch_mcp_tool_call
from agent_sudo.models import ActionRequest, ApprovalStatus, Classification, Decision
from agent_sudo.pending_approvals import (
    DEFAULT_APPROVAL_TTL_SECONDS,
    MAX_APPROVAL_TTL_SECONDS,
    MIN_APPROVAL_TTL_SECONDS,
    PendingApprovalStore,
    resolve_approval_ttl_seconds,
)
from agent_sudo.policy import load_default_policy


class PendingApprovalWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def _critical_tool_call(self) -> dict[str, str]:
        return {
            "actor": "mcp-client",
            "source": "user",
            "tool": "shell",
            "action": "run_shell_command",
            "target": "pwd",
            "payload_summary": "show current directory",
        }

    def _config_path(self, tmpdir: str, passphrase: str = "test-passphrase") -> Path:
        path = Path(tmpdir) / "config.json"
        path.write_text(json.dumps(hash_passphrase(passphrase, salt=b"1" * 16)), encoding="utf-8")
        return path

    def test_non_interactive_mcp_critical_action_creates_pending_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            store = PendingApprovalStore(Path(tmpdir) / "pending.json", audit_logger=AuditLogger(audit_path))
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )

            result = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approvals = store.list()

        self.assertFalse(result.executed)
        self.assertEqual(result.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0].status, ApprovalStatus.PENDING)
        self.assertEqual(store.ttl_seconds, DEFAULT_APPROVAL_TTL_SECONDS)
        self.assertEqual(result.gateway_result.approval_request_id, approvals[0].approval_request_id)
        self.assertIn("agent-sudo approve", result.gateway_result.approval_command)
        self.assertEqual(result.gateway_result.approval_expires_at, approvals[0].expires_at)
        self.assertIsNotNone(result.gateway_result.approval_expires_in_seconds)

    def test_approval_list_shows_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(["approvals", "list", "--pending-approvals-file", str(pending_path)])

        self.assertEqual(code, 0)
        self.assertIn("run_shell_command", output.getvalue())
        self.assertIn("PENDING", output.getvalue())

    def test_pending_lists_active_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            output = io.StringIO()

            with redirect_stdout(output):
                code = main(["pending", "--pending-approvals-file", str(pending_path)])

        self.assertEqual(code, 0)
        self.assertIn("approval_id", output.getvalue())
        self.assertIn("run_shell_command", output.getvalue())
        self.assertIn("CRITICAL", output.getvalue())

    def test_approve_with_passphrase_marks_approved_retry_executes_once_then_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path, audit_logger=AuditLogger(audit_path))
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approval_id = initial.gateway_result.approval_request_id
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            approved, approval_result = store.approve(approval_id, approval_provider=provider)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            second_retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            audit_events = [
                json.loads(line)["event_type"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(approval_result.approved)
        self.assertIsNotNone(approved)
        self.assertEqual(approved.status, ApprovalStatus.APPROVED)
        self.assertTrue(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.ALLOW)
        self.assertEqual(retry.gateway_result.approval_method, "PENDING_APPROVAL")
        self.assertFalse(second_retry.executed)
        self.assertEqual(second_retry.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertNotEqual(second_retry.gateway_result.approval_request_id, approval_id)
        self.assertIn("approval_created", audit_events)
        self.assertIn("approval_approved", audit_events)
        self.assertIn("approval_used", audit_events)
        self.assertEqual(audit_events.count("gateway_decision"), 3)

    def test_approve_by_short_index_marks_request_approved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            config_path = self._config_path(tmpdir)
            store = PendingApprovalStore(pending_path)
            store.create(
                action_request=ActionRequest(
                    actor="mcp-client",
                    source="user",
                    tool="filesystem",
                    action="write_file",
                    target="/tmp/agent-sudo-demo/test.txt",
                    payload_summary="write demo file",
                ),
                classification=Classification.SENSITIVE,
                decision=Decision.REQUIRE_APPROVAL,
                required_approval_method="CLI_CONFIRM",
                reason="SENSITIVE actions require CLI approval",
            )

            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "approve",
                        "1",
                        "--pending-approvals-file",
                        str(pending_path),
                        "--approval-config",
                        str(config_path),
                    ]
                )
            approved = PendingApprovalStore(pending_path).list()[0]

        self.assertEqual(code, 0)
        self.assertEqual(approved.status, ApprovalStatus.APPROVED)

    def test_short_index_approval_consumes_expected_request_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            config_path = self._config_path(tmpdir)
            store = PendingApprovalStore(pending_path)
            first = store.create(
                action_request=ActionRequest(
                    actor="mcp-client",
                    source="user",
                    tool="filesystem",
                    action="write_file",
                    target="/tmp/agent-sudo-demo/first.txt",
                    payload_summary="write first demo file",
                ),
                classification=Classification.SENSITIVE,
                decision=Decision.REQUIRE_APPROVAL,
                required_approval_method="CLI_CONFIRM",
                reason="SENSITIVE actions require CLI approval",
            )
            second = store.create(
                action_request=ActionRequest(
                    actor="mcp-client",
                    source="user",
                    tool="filesystem",
                    action="write_file",
                    target="/tmp/agent-sudo-demo/second.txt",
                    payload_summary="write second demo file",
                ),
                classification=Classification.SENSITIVE,
                decision=Decision.REQUIRE_APPROVAL,
                required_approval_method="CLI_CONFIRM",
                reason="SENSITIVE actions require CLI approval",
            )

            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "approve",
                        "2",
                        "--pending-approvals-file",
                        str(pending_path),
                        "--approval-config",
                        str(config_path),
                    ]
                )
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=PendingApprovalStore(pending_path),
            )
            second_retry = gateway.evaluate(second.action_request)
            first_after_second_retry = PendingApprovalStore(pending_path).list()[0]
            second_after_second_retry = PendingApprovalStore(pending_path).list()[1]
            first_retry = gateway.evaluate(first.action_request)
            final_approvals = PendingApprovalStore(pending_path).list()

        self.assertEqual(code, 0)
        self.assertEqual(second_retry.decision, Decision.ALLOW)
        self.assertEqual(second_retry.approval_request_id, second.approval_request_id)
        self.assertEqual(first_after_second_retry.status, ApprovalStatus.PENDING)
        self.assertEqual(second_after_second_retry.status, ApprovalStatus.USED)
        self.assertEqual(first_retry.decision, Decision.REQUIRE_APPROVAL)
        self.assertEqual(first_retry.approval_request_id, first.approval_request_id)
        self.assertEqual(final_approvals[0].status, ApprovalStatus.PENDING)
        self.assertEqual(final_approvals[1].status, ApprovalStatus.USED)

    def test_retry_with_new_request_id_uses_approved_request_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            first_call = dict(self._critical_tool_call(), request_id="jsonrpc-1")
            retry_call = dict(self._critical_tool_call(), request_id="jsonrpc-2")
            initial = dispatch_mcp_tool_call(first_call, gateway)
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            store.approve(initial.gateway_result.approval_request_id, approval_provider=provider)
            retry = dispatch_mcp_tool_call(retry_call, gateway)
            second_retry = dispatch_mcp_tool_call(retry_call, gateway)

        self.assertTrue(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.ALLOW)
        self.assertFalse(second_retry.executed)
        self.assertEqual(second_retry.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)

    def test_denial_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            denied = store.deny(initial.gateway_result.approval_request_id)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)

        self.assertIsNotNone(denied)
        self.assertEqual(denied.status, ApprovalStatus.DENIED)
        self.assertFalse(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertNotEqual(retry.gateway_result.approval_request_id, initial.gateway_result.approval_request_id)

    def test_expiration_blocks_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store = PendingApprovalStore(pending_path, ttl_seconds=30, now_func=lambda: now)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            now = now + timedelta(seconds=31)
            retry = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            approvals = store.list()

        self.assertFalse(initial.executed)
        self.assertFalse(retry.executed)
        self.assertEqual(retry.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
        self.assertEqual(approvals[0].status, ApprovalStatus.EXPIRED)
        self.assertNotEqual(retry.gateway_result.approval_request_id, initial.gateway_result.approval_request_id)

    def test_approval_remains_valid_for_configured_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store = PendingApprovalStore(pending_path, ttl_seconds=120, now_func=lambda: now)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            now = now + timedelta(seconds=119)
            approved, result = store.approve(initial.gateway_result.approval_request_id, approval_provider=provider)

        self.assertTrue(result.approved)
        self.assertIsNotNone(approved)
        self.assertEqual(approved.status, ApprovalStatus.APPROVED)

    def test_ttl_config_bounds(self) -> None:
        self.assertEqual(resolve_approval_ttl_seconds(None), DEFAULT_APPROVAL_TTL_SECONDS)
        self.assertEqual(resolve_approval_ttl_seconds(1), MIN_APPROVAL_TTL_SECONDS)
        self.assertEqual(resolve_approval_ttl_seconds(9999), MAX_APPROVAL_TTL_SECONDS)
        self.assertEqual(resolve_approval_ttl_seconds("not-an-int"), DEFAULT_APPROVAL_TTL_SECONDS)
        with patch.dict("os.environ", {"AGENT_SUDO_APPROVAL_TTL_SECONDS": "240"}):
            self.assertEqual(resolve_approval_ttl_seconds(None), 240)

    def test_mcp_structured_approval_response_contains_id_and_expiry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            server = build_server(
                pending_approvals_file=pending_path,
                audit_log=Path(tmpdir) / "audit.jsonl",
                approval_ttl_seconds=120,
            )
            response = server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "shell",
                    "method": "tools/call",
                    "params": {"name": "run_shell_command", "arguments": {"command": "pwd"}},
                }
            )
            structured = response["result"]["structuredContent"]

        self.assertEqual(structured["status"], "approval_required")
        self.assertTrue(structured["approval_id"])
        self.assertTrue(structured["approval_command"].startswith("agent-sudo approve "))
        self.assertTrue(structured["expires_at"])
        self.assertIsNotNone(structured["expires_in_seconds"])
        self.assertIn("run_shell_command", structured["action_summary"])
        self.assertEqual(structured["risk"], "CRITICAL")

    def test_audit_logs_denied_and_expired_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            audit_path = Path(tmpdir) / "audit.jsonl"
            store = PendingApprovalStore(
                Path(tmpdir) / "pending.json",
                audit_logger=AuditLogger(audit_path),
                ttl_seconds=-1,
            )
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                audit_logger=AuditLogger(audit_path),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            store.deny(initial.gateway_result.approval_request_id)
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            events = [
                json.loads(line)["event_type"]
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertIn("approval_created", events)
        self.assertIn("approval_denied", events)
        self.assertIn("gateway_decision", events)

    def test_used_approvals_ignored_during_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            store.approve(initial.gateway_result.approval_request_id, approval_provider=provider)
            # Consume
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)

            # Lookup should ignore USED approval
            match = store.find_matching(ActionRequest.from_dict(self._critical_tool_call()))
            self.assertIsNone(match)

    def test_expired_approvals_ignored_during_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            store.deny(initial.gateway_result.approval_request_id, reason="expired")
            # Force set status to EXPIRED to test EXPIRED matching
            approvals = store.list(update_expired=False)
            from dataclasses import replace
            store.save([replace(a, status=ApprovalStatus.EXPIRED) for a in approvals])

            match = store.find_matching(ActionRequest.from_dict(self._critical_tool_call()))
            self.assertIsNone(match)

    def test_denied_approvals_ignored_during_matching(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            store.deny(initial.gateway_result.approval_request_id)

            match = store.find_matching(ActionRequest.from_dict(self._critical_tool_call()))
            self.assertIsNone(match)

    def test_same_command_after_used_creates_new_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            first_id = initial.gateway_result.approval_request_id

            provider = ApprovalProvider(
                config_path=self._config_path(tmpdir),
                getpass_func=lambda prompt: "test-passphrase",
                stdin_is_tty=lambda: True,
            )
            store.approve(first_id, approval_provider=provider)
            # Consume
            dispatch_mcp_tool_call(self._critical_tool_call(), gateway)

            # Second call creates a new approval
            second = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            second_id = second.gateway_result.approval_request_id

            self.assertEqual(second.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
            self.assertNotEqual(first_id, second_id)
            self.assertTrue(second_id)

    def test_same_command_after_expired_creates_new_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            now = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store = PendingApprovalStore(pending_path, ttl_seconds=30, now_func=lambda: now)
            gateway = PermissionGateway(
                self.policy,
                approvals=ApprovalProvider(stdin_is_tty=lambda: False),
                pending_approval_store=store,
            )
            initial = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            first_id = initial.gateway_result.approval_request_id

            # Expire
            now = now + timedelta(seconds=31)

            # Second call creates a new approval
            second = dispatch_mcp_tool_call(self._critical_tool_call(), gateway)
            second_id = second.gateway_result.approval_request_id

            self.assertEqual(second.gateway_result.decision, Decision.REQUIRE_STRONG_APPROVAL)
            self.assertNotEqual(first_id, second_id)
            self.assertTrue(second_id)

    def test_multiple_historical_approvals_with_same_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            req = ActionRequest.from_dict(self._critical_tool_call())

            # Create historical EXPIRED and USED approvals
            store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="stale",
            )
            store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="stale",
            )

            approvals = store.list(update_expired=False)
            from dataclasses import replace
            store.save([
                replace(approvals[0], status=ApprovalStatus.EXPIRED),
                replace(approvals[1], status=ApprovalStatus.USED),
            ])

            match = store.find_matching(req)
            self.assertIsNone(match)

    def test_most_recent_active_approval_selected_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            store = PendingApprovalStore(pending_path)
            req = ActionRequest.from_dict(self._critical_tool_call())

            # 1. Stale USED
            store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="stale",
            )
            # 2. First active
            active1 = store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="active1",
            )
            # 3. Second active (newer)
            active2 = store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="active2",
            )

            approvals = store.list(update_expired=False)
            from dataclasses import replace
            store.save([
                replace(approvals[0], status=ApprovalStatus.USED),
                approvals[1],
                approvals[2],
            ])

            match = store.find_matching(req)
            self.assertIsNotNone(match)
            self.assertEqual(match.approval_request_id, active2.approval_request_id)
            self.assertEqual(match.reason, "active2")

    def test_approve_command_wrong_passphrase_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            config_path = self._config_path(tmpdir, passphrase="correct-passphrase")
            store = PendingApprovalStore(pending_path)
            req = ActionRequest.from_dict(self._critical_tool_call())
            app = store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="strong approval required",
            )

            # We need to mock ApprovalProvider to simulate inputting a WRONG passphrase
            from unittest.mock import patch
            from agent_sudo.approvals import ApprovalProvider

            original_init = ApprovalProvider.__init__
            def custom_init(self, *args, **kwargs):
                original_init(self, *args, **kwargs)
                self.getpass_func = lambda prompt: "wrong-passphrase"
                self.stdin_is_tty = lambda: True

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(ApprovalProvider, "__init__", custom_init), \
                 redirect_stdout(stdout), \
                 redirect_stderr(stderr):
                code = main([
                    "approve", "1",
                    "--pending-approvals-file", str(pending_path),
                    "--approval-config", str(config_path),
                ])

            self.assertEqual(code, 1)
            self.assertIn("Error: passphrase verification failed", stderr.getvalue())
            self.assertEqual(stdout.getvalue().strip(), "") # No misleading JSON
            # Verify status on disk remains PENDING
            self.assertEqual(store.list(update_expired=False)[0].status, ApprovalStatus.PENDING)

    def test_approve_command_expired_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            config_path = self._config_path(tmpdir)
            # Create a store with a tiny TTL so we can mock/expire it, or just write it already expired
            store = PendingApprovalStore(pending_path)
            req = ActionRequest.from_dict(self._critical_tool_call())

            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)
            from agent_sudo.pending_approvals import _format_time
            # Directly inject an expired pending request on disk
            from agent_sudo.models import ApprovalRequest
            import uuid
            app = ApprovalRequest(
                approval_request_id=str(uuid.uuid4()),
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                created_at=_format_time(now - timedelta(seconds=120)),
                expires_at=_format_time(now - timedelta(seconds=10)),
                status=ApprovalStatus.PENDING,
                reason="strong approval required",
            )
            store.save([app])

            # Try approving via CLI
            from unittest.mock import patch
            from agent_sudo.approvals import ApprovalProvider

            original_init = ApprovalProvider.__init__
            def custom_init(self, *args, **kwargs):
                original_init(self, *args, **kwargs)
                self.getpass_func = lambda prompt: "test-passphrase"
                self.stdin_is_tty = lambda: True

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(ApprovalProvider, "__init__", custom_init), \
                 redirect_stdout(stdout), \
                 redirect_stderr(stderr):
                code = main([
                    "approve", app.approval_request_id,
                    "--pending-approvals-file", str(pending_path),
                    "--approval-config", str(config_path),
                ])

            self.assertEqual(code, 1)
            self.assertIn("Error: approval request is EXPIRED", stderr.getvalue())
            self.assertEqual(stdout.getvalue().strip(), "") # No misleading JSON
            self.assertEqual(store.list(update_expired=False)[0].status, ApprovalStatus.EXPIRED)

    def test_approve_command_success_visibility(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pending_path = Path(tmpdir) / "pending.json"
            config_path = self._config_path(tmpdir, passphrase="test-passphrase")
            store = PendingApprovalStore(pending_path)
            req = ActionRequest.from_dict(self._critical_tool_call())
            app = store.create(
                action_request=req,
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="strong approval required",
            )

            # We need to mock ApprovalProvider to simulate inputting the correct passphrase
            from unittest.mock import patch
            from agent_sudo.approvals import ApprovalProvider

            original_init = ApprovalProvider.__init__
            def custom_init(self, *args, **kwargs):
                original_init(self, *args, **kwargs)
                self.getpass_func = lambda prompt: "test-passphrase"
                self.stdin_is_tty = lambda: True

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch.object(ApprovalProvider, "__init__", custom_init), \
                 redirect_stdout(stdout), \
                 redirect_stderr(stderr):
                code = main([
                    "approve", "1",
                    "--pending-approvals-file", str(pending_path),
                    "--approval-config", str(config_path),
                ])

            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue().strip(), "")
            # Successful approval prints JSON to stdout
            out_json = json.loads(stdout.getvalue().strip())
            self.assertEqual(out_json["status"], "APPROVED")
            # Verify status on disk persists as APPROVED
            self.assertEqual(store.list(update_expired=False)[0].status, ApprovalStatus.APPROVED)


if __name__ == "__main__":
    unittest.main()
