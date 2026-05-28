from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_sudo.models import ActionRequest, Classification, Decision, ApprovalStatus
from agent_sudo.pending_approvals import PendingApprovalStore
from agent_sudo.helper import run_approval_helper
from agent_sudo.notifications import open_approval_terminal_window


class ApprovalHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name).resolve()
        self.pending_file = self.tmp_path / "pending_approvals.json"
        self.config_file = self.tmp_path / "config.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _sample_action_request(self, action="run_shell_command", target="pwd") -> ActionRequest:
        return ActionRequest(
            actor="mcp-client",
            source="user",
            tool="shell",
            action=action,
            target=target,
            payload_summary="Run shell command",
        )

    def test_helper_shows_setup_guidance_when_config_missing(self) -> None:
        # Passphrase config doesn't exist
        err_stream = io.StringIO()
        with patch("sys.stderr", err_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
            )
        self.assertEqual(code, 1)
        output = err_stream.getvalue()
        self.assertIn("No approval passphrase configuration found.", output)
        self.assertIn("agent-sudo init-approval", output)
        self.assertIn("passphrase cannot be recovered", output)

    def test_helper_handles_no_pending_approvals(self) -> None:
        # Create config file so helper continues
        self.config_file.write_text("{}", encoding="utf-8")
        out_stream = io.StringIO()
        with patch("sys.stdout", out_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
            )
        self.assertEqual(code, 0)
        self.assertIn("No active pending approvals.", out_stream.getvalue())

    def test_helper_shows_pending_approvals_and_interactive_y(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")

        # Create a pending approval
        store = PendingApprovalStore(self.pending_file)
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical action",
        )

        out_stream = io.StringIO()
        # Mock inputs and store approval checks
        mock_input = MagicMock(return_value="y")
        mock_approve = MagicMock(return_value=(MagicMock(), MagicMock(approved=True)))

        with patch("sys.stdout", out_stream), \
             patch("agent_sudo.pending_approvals.PendingApprovalStore.approve", mock_approve):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
            )

        self.assertEqual(code, 0)
        output = out_stream.getvalue()
        self.assertIn("Active pending approvals:", output)
        self.assertIn("run_shell_command", output)
        self.assertIn("agent-sudo approve", output)
        mock_approve.assert_called_once()

    def test_helper_interactive_n(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")

        store = PendingApprovalStore(self.pending_file)
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.SENSITIVE,
            decision=Decision.REQUIRE_APPROVAL,
            required_approval_method="CLI_CONFIRM",
            reason="sensitive action",
        )

        out_stream = io.StringIO()
        mock_input = MagicMock(return_value="n")
        mock_deny = MagicMock()

        with patch("sys.stdout", out_stream), \
             patch("agent_sudo.pending_approvals.PendingApprovalStore.deny", mock_deny):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
            )

        self.assertEqual(code, 0)
        self.assertIn("Request #1 denied.", out_stream.getvalue())
        mock_deny.assert_called_once()

    @patch("sys.platform", "darwin")
    @patch("subprocess.run")
    def test_open_terminal_enabled_triggers_macos_opener(self, mock_run) -> None:
        mock_run.return_value = MagicMock(returncode=0)
        
        # Test default is OFF
        with patch.dict("os.environ", {}, clear=True):
            store = PendingApprovalStore(self.pending_file)
            self.assertFalse(store.open_approval_terminal)

        # Test enable via env
        with patch.dict("os.environ", {"AGENT_SUDO_OPEN_APPROVAL_TERMINAL": "1"}):
            store = PendingApprovalStore(self.pending_file)
            self.assertTrue(store.open_approval_terminal)

            # Creating a pending approval triggers the opener
            store.create(
                action_request=self._sample_action_request(),
                classification=Classification.CRITICAL,
                decision=Decision.REQUIRE_STRONG_APPROVAL,
                required_approval_method="PASSPHRASE_CONFIRM",
                reason="critical action",
            )

        mock_run.assert_called_once()
        args, kwargs = mock_run.call_args
        command_list = args[0]
        self.assertEqual(command_list[0], "osascript")
        self.assertEqual(command_list[1], "-e")
        
        script_content = command_list[2]
        self.assertIn("tell application \"Terminal\"", script_content)
        self.assertIn("do script", script_content)
        self.assertIn("approval-helper", script_content)
        self.assertIn(str(self.pending_file.resolve()), script_content)
        self.assertNotIn("pwd", script_content)  # does not contain target secrets
        self.assertEqual(kwargs.get("shell"), None)  # shell=True not used

    @patch("sys.platform", "darwin")
    @patch("subprocess.run")
    def test_opener_failure_does_not_break_approval_creation(self, mock_run) -> None:
        mock_run.side_effect = Exception("AppleScript execution crashed")
        
        store = PendingApprovalStore(self.pending_file, open_approval_terminal=True)
        # Should not raise exception
        approval = store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical action",
        )
        self.assertEqual(len(store.list()), 1)


if __name__ == "__main__":
    unittest.main()
