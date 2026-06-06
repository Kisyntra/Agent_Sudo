from __future__ import annotations

import io
import re
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_sudo.models import ActionRequest, Classification, Decision
from agent_sudo.pending_approvals import PendingApprovalStore
from agent_sudo.helper import run_approval_helper


class ApprovalHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name).resolve()
        self.pending_file = self.tmp_path / "pending_approvals.json"
        self.config_file = self.tmp_path / "config.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _sample_action_request(
        self, action="run_shell_command", target="pwd"
    ) -> ActionRequest:
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

        with (
            patch("sys.stdout", out_stream),
            patch(
                "agent_sudo.pending_approvals.PendingApprovalStore.approve",
                mock_approve,
            ),
        ):
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

        with (
            patch("sys.stdout", out_stream),
            patch("agent_sudo.pending_approvals.PendingApprovalStore.deny", mock_deny),
        ):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
            )

        self.assertEqual(code, 0)
        self.assertIn("Request #1 denied.", out_stream.getvalue())
        mock_deny.assert_called_once()

    def test_auto_opened_prompt_uses_expires_in_wording(self) -> None:
        # The auto-opened terminal renders per-request details; the expiry line
        # must read "Expires in ~Ns — approve before then." (issue #88).
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
        with (
            patch("sys.stdout", out_stream),
            patch(
                "agent_sudo.pending_approvals.PendingApprovalStore.deny", MagicMock()
            ),
        ):
            run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        output = out_stream.getvalue()
        self.assertIn("Expires in ~", output)
        self.assertIn("approve before then", output)

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
        self.assertIn('tell application "Terminal"', script_content)
        self.assertIn("do script", script_content)
        self.assertIn("approval-helper", script_content)
        self.assertIn(str(self.pending_file.resolve()), script_content)
        self.assertEqual(kwargs.get("shell"), None)  # shell=True not used
        self.assertIn("--auto-opened", script_content)
        self.assertIn("clear; exec ", script_content)

        # Security: the auto-opened Terminal must launch ONLY the approval-helper,
        # never the command being approved (here `run_shell_command pwd`). Parse the
        # single `do script` body and assert its command structure exactly, rather
        # than substring-scanning the whole script for "pwd" — a brittle check that
        # false-positives whenever the temp-dir path happens to contain that string.
        do_script_match = re.search(r'do script "(.*?)"', script_content)
        self.assertIsNotNone(do_script_match)
        shell_commands = [c.strip() for c in do_script_match.group(1).split(";")]
        self.assertEqual(len(shell_commands), 2)  # only `clear` and `exec ...`
        self.assertEqual(shell_commands[0], "clear")
        self.assertTrue(shell_commands[1].startswith("exec "))
        exec_tokens = shlex.split(shell_commands[1][len("exec ") :])
        self.assertEqual(
            exec_tokens,
            [
                sys.executable,
                "-m",
                "agent_sudo.gateway",
                "approval-helper",
                "--auto-opened",
                "--pending-approvals-file",
                str(self.pending_file.resolve()),
            ],
        )

    @patch("sys.platform", "darwin")
    @patch("subprocess.run")
    def test_opener_failure_does_not_break_approval_creation(self, mock_run) -> None:
        mock_run.side_effect = Exception("AppleScript execution crashed")

        store = PendingApprovalStore(self.pending_file, open_approval_terminal=True)
        # Should not raise exception
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical action",
        )
        self.assertEqual(len(store.list()), 1)

    def test_helper_auto_opened_minimal_details(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        store = PendingApprovalStore(self.pending_file)

        # 1. Shell command target with absolute path
        store.create(
            action_request=self._sample_action_request(
                action="run_shell_command", target="/usr/bin/python3 -c 'print(1)'"
            ),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical",
        )

        out_stream = io.StringIO()
        mock_input = MagicMock(return_value="n")  # deny to complete
        with patch("sys.stdout", out_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        self.assertEqual(code, 0)
        output = out_stream.getvalue()
        self.assertIn("Agent_Sudo approval required", output)
        self.assertIn("Target:    python3", output)  # extracts command basename
        self.assertNotIn("/usr/bin/python3", output)

    @patch("time.sleep")
    def test_helper_auto_opened_successful_approval_triggers_countdown(
        self, mock_sleep
    ) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        store = PendingApprovalStore(self.pending_file)
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical",
        )

        out_stream = io.StringIO()
        mock_input = MagicMock(return_value="y")
        from agent_sudo.models import ApprovalResult

        mock_approve_critical = MagicMock(
            return_value=ApprovalResult(approved=True, method="MOCK", reason="approved")
        )

        with (
            patch("sys.stdout", out_stream),
            patch(
                "agent_sudo.approvals.ApprovalProvider.approve_critical",
                mock_approve_critical,
            ),
        ):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        self.assertEqual(code, 0)
        output = out_stream.getvalue()
        self.assertIn("Approved. Closing in 3 seconds...", output)
        mock_sleep.assert_called_once_with(3.0)

    @patch("time.sleep")
    def test_helper_auto_opened_denial_triggers_countdown(self, mock_sleep) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        store = PendingApprovalStore(self.pending_file)
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical",
        )

        out_stream = io.StringIO()
        mock_input = MagicMock(return_value="n")

        with patch("sys.stdout", out_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        self.assertEqual(code, 0)
        output = out_stream.getvalue()
        self.assertIn("Denied. Closing in 3 seconds...", output)
        mock_sleep.assert_called_once_with(3.0)

    def test_helper_auto_opened_failed_verification_does_not_close(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        store = PendingApprovalStore(self.pending_file)
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical",
        )

        out_stream = io.StringIO()
        # Mock inputs: first "y" for approval prompt, second "" (Enter) for blocking exit prompt
        mock_input = MagicMock(side_effect=["y", ""])
        mock_approve = MagicMock(
            return_value=(
                None,
                MagicMock(approved=False, reason="incorrect passphrase"),
            )
        )

        with (
            patch("sys.stdout", out_stream),
            patch(
                "agent_sudo.pending_approvals.PendingApprovalStore.approve",
                mock_approve,
            ),
            patch("time.sleep") as mock_sleep,
        ):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        self.assertEqual(code, 0)
        output = out_stream.getvalue()
        self.assertIn("Approval failed: incorrect passphrase", output)
        self.assertEqual(mock_input.call_count, 2)  # both prompts were processed
        mock_sleep.assert_not_called()

    def test_helper_auto_opened_multiple_requests_do_not_close(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        store = PendingApprovalStore(self.pending_file)
        # Create two requests
        store.create(
            action_request=self._sample_action_request(),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical 1",
        )
        store.create(
            action_request=self._sample_action_request(target="ls"),
            classification=Classification.CRITICAL,
            decision=Decision.REQUIRE_STRONG_APPROVAL,
            required_approval_method="PASSPHRASE_CONFIRM",
            reason="critical 2",
        )

        out_stream = io.StringIO()
        # 1st request approve prompt -> "y"
        # 2nd request approve prompt -> "y"
        # Blocking exit prompt -> ""
        mock_input = MagicMock(side_effect=["y", "y", ""])
        mock_approve = MagicMock(return_value=(MagicMock(), MagicMock(approved=True)))

        with (
            patch("sys.stdout", out_stream),
            patch(
                "agent_sudo.pending_approvals.PendingApprovalStore.approve",
                mock_approve,
            ),
            patch("time.sleep") as mock_sleep,
        ):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )

        self.assertEqual(code, 0)
        mock_sleep.assert_not_called()
        self.assertEqual(mock_input.call_count, 3)  # "y", "y", then exit prompt

    def test_helper_auto_opened_no_config_blocks_enter(self) -> None:
        # Config path does not exist
        err_stream = io.StringIO()
        mock_input = MagicMock(return_value="")
        with patch("sys.stderr", err_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )
        self.assertEqual(code, 1)
        mock_input.assert_called_once_with("\nPress Enter to exit...")

    def test_helper_auto_opened_no_pending_blocks_enter(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        out_stream = io.StringIO()
        mock_input = MagicMock(return_value="")
        with patch("sys.stdout", out_stream):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )
        self.assertEqual(code, 0)
        self.assertIn("No active pending approvals.", out_stream.getvalue())
        mock_input.assert_called_once_with("\nPress Enter to exit...")

    def test_helper_auto_opened_unexpected_error_blocks_enter(self) -> None:
        self.config_file.write_text("{}", encoding="utf-8")
        mock_input = MagicMock(return_value="")

        # Force exception by making store.list raise a ValueError
        with (
            patch(
                "agent_sudo.pending_approvals.PendingApprovalStore.list",
                side_effect=ValueError("crashed"),
            ),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            code = run_approval_helper(
                pending_approvals_path=self.pending_file,
                config_path=self.config_file,
                input_func=mock_input,
                auto_opened=True,
            )
        self.assertEqual(code, 1)
        mock_input.assert_called_once_with("\nPress Enter to exit...")


if __name__ == "__main__":
    unittest.main()
