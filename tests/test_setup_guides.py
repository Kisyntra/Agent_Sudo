from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from agent_sudo.gateway import main
from agent_sudo.setup_guides import (
    MCP_SETUP_TARGETS,
    SETUP_TARGETS,
    _mcp_state_paths,
    render_setup,
    resolve_mcp_command,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


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
        with mock.patch("agent_sudo.setup_guides.shutil.which", return_value=resolved):
            codex = render_setup("codex")
            claude_code = render_setup("claude-code")

        self.assertIn(resolved, codex)
        self.assertIn(resolved, claude_code)

    def test_resolve_mcp_command_falls_back_to_bare_name(self) -> None:
        with (
            mock.patch("agent_sudo.setup_guides.shutil.which", return_value=None),
            mock.patch("agent_sudo.setup_guides.Path.exists", return_value=False),
        ):
            self.assertEqual(resolve_mcp_command(), "agent-sudo-mcp")

    def test_setup_claude_desktop_prints_pasteable_json(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["setup", "claude-desktop"])
        text = output.getvalue()

        self.assertEqual(code, 0)
        self.assertIn("dry-run only", text)
        # Pasteable JSON, not a prose checklist.
        self.assertIn('"mcpServers"', text)
        self.assertIn('"command":', text)
        self.assertIn('"args":', text)
        self.assertNotIn("1. ", text)

    def test_all_mcp_configs_include_delegations_file(self) -> None:
        # Without --delegations-file the server runs with no delegation store
        # and tokens are silently ignored, so every MCP config must include it.
        _, _, delegations = _mcp_state_paths()
        for target in MCP_SETUP_TARGETS:
            text = render_setup(target)
            self.assertIn("--delegations-file", text, target)
            self.assertIn(delegations, text, target)
            self.assertIn("/.agent-sudo/delegations.json", text, target)

    def test_mcp_config_pins_absolute_audit_and_pending_paths(self) -> None:
        # Relative audit-log defaults would land where the verify step cannot
        # read them; setup must pin absolute paths under ~/.agent-sudo.
        for target in MCP_SETUP_TARGETS:
            text = render_setup(target)
            self.assertIn("--audit-log", text, target)
            self.assertIn("--pending-approvals-file", text, target)
            self.assertIn("/.agent-sudo/mcp-audit.jsonl", text, target)

    def test_verify_command_uses_the_generated_audit_path(self) -> None:
        # The audit-log path in the config must be the exact path the verify
        # instruction tells the user to inspect (so it cannot be misleading).
        audit_log, _, _ = _mcp_state_paths()
        for target in MCP_SETUP_TARGETS:
            text = render_setup(target)
            # Appears once in the config args and once in the verify command.
            self.assertGreaterEqual(text.count(audit_log), 2, target)
            self.assertIn(f"agent-sudo audit list {audit_log}", text, target)

    def test_macos_emits_interactive_approval_flags(self) -> None:
        with mock.patch("agent_sudo.setup_guides.sys.platform", "darwin"):
            for target in MCP_SETUP_TARGETS:
                text = render_setup(target)
                self.assertIn("--notify", text, target)
                self.assertIn("--open-approval-terminal", text, target)

    def test_non_macos_omits_macos_only_flags(self) -> None:
        with mock.patch("agent_sudo.setup_guides.sys.platform", "linux"):
            for target in MCP_SETUP_TARGETS:
                text = render_setup(target)
                self.assertNotIn("--open-approval-terminal", text, target)
                self.assertNotIn("--notify", text, target)

    def test_readme_claude_desktop_config_has_no_empty_args(self) -> None:
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn('"args": []', readme)
        # The recommended README config must wire delegations.
        self.assertIn("--delegations-file", readme)

    def test_docs_state_macos_only_platform_support(self) -> None:
        # README and the MCP setup doc must state the macOS-only flags and the
        # manual cross-platform approval workflow, and must not promise icons.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        mcp_doc = (
            REPO_ROOT / "docs" / "integrations" / "mcp_server_setup.md"
        ).read_text(encoding="utf-8")
        for text in (readme, mcp_doc):
            self.assertIn("macOS-only", text)
            self.assertIn("agent-sudo approve", text)
            self.assertIn("no custom", text.lower())

    def test_prose_targets_still_render_numbered_checklist(self) -> None:
        # hermes/openclaw remain native-wrap prose checklists.
        text = render_setup("openclaw")
        self.assertIn("dry-run only", text)
        self.assertIn("1. ", text)


if __name__ == "__main__":
    unittest.main()
