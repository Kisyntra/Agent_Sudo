from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from agent_sudo.gateway import main
from agent_sudo.setup_guides import (
    SETUP_TARGETS,
    render_setup,
    resolve_mcp_command,
)


class SetupGuideTests(unittest.TestCase):
    def test_claude_code_is_a_supported_target(self) -> None:
        self.assertIn("claude-code", SETUP_TARGETS)

    def test_setup_claude_code_prints_pasteable_add_command(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["setup", "claude-code"])
        text = output.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("dry-run only", text)
        # A single, pasteable command using the -- server-command separator.
        self.assertIn("claude mcp add agent-sudo --", text)
        self.assertIn("agent-sudo-mcp", text)
        # Verification and removal guidance are both present.
        self.assertIn("claude mcp list", text)
        self.assertIn("claude mcp remove agent-sudo", text)

    def test_setup_codex_prints_pasteable_toml(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["setup", "codex"])
        text = output.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("dry-run only", text)
        # Concrete TOML, not a prose checklist.
        self.assertIn("~/.codex/config.toml", text)
        self.assertIn("[mcp_servers.agent-sudo]", text)
        self.assertIn("command = ", text)
        self.assertIn("args = ", text)
        self.assertIn("Verify with:", text)
        # Numbered prose checklist markers must be gone for this target.
        self.assertNotIn("1. ", text)

    def test_setup_uses_resolved_executable_path(self) -> None:
        resolved = "/opt/example/bin/agent-sudo-mcp"
        with mock.patch(
            "agent_sudo.setup_guides.shutil.which", return_value=resolved
        ):
            codex = render_setup("codex")
            claude_code = render_setup("claude-code")

        self.assertIn(resolved, codex)
        self.assertIn(resolved, claude_code)

    def test_resolve_mcp_command_falls_back_to_bare_name(self) -> None:
        with mock.patch(
            "agent_sudo.setup_guides.shutil.which", return_value=None
        ), mock.patch("agent_sudo.setup_guides.Path.exists", return_value=False):
            self.assertEqual(resolve_mcp_command(), "agent-sudo-mcp")

    def test_mcp_config_pins_absolute_audit_and_pending_paths(self) -> None:
        # Relative audit-log defaults would land where the verify step cannot
        # read them; setup must pin absolute paths under ~/.agent-sudo.
        for target in ("codex", "claude-code"):
            text = render_setup(target)
            self.assertIn("--audit-log", text)
            self.assertIn("--pending-approvals-file", text)
            self.assertIn("/.agent-sudo/mcp-audit.jsonl", text)
            # The verify command references that same absolute audit path.
            self.assertIn("agent-sudo audit list /", text)

    def test_macos_emits_interactive_approval_flags(self) -> None:
        with mock.patch("agent_sudo.setup_guides.sys.platform", "darwin"):
            for target in ("codex", "claude-code"):
                text = render_setup(target)
                self.assertIn("--notify", text)
                self.assertIn("--open-approval-terminal", text)

    def test_non_macos_omits_macos_only_flags(self) -> None:
        with mock.patch("agent_sudo.setup_guides.sys.platform", "linux"):
            for target in ("codex", "claude-code"):
                text = render_setup(target)
                self.assertNotIn("--open-approval-terminal", text)
                self.assertNotIn("--notify", text)

    def test_prose_targets_still_render_numbered_checklist(self) -> None:
        text = render_setup("claude-desktop")
        self.assertIn("dry-run only", text)
        self.assertIn("1. ", text)


if __name__ == "__main__":
    unittest.main()
