from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from agent_sudo.adapters.claude_desktop import from_claude_desktop_tool_call
from agent_sudo.adapters.generic import from_generic_tool_call
from agent_sudo.adapters.mcp import from_mcp_tool_call
from agent_sudo.adapters.openclaw import from_openclaw_tool_call
from agent_sudo.gateway import PermissionGateway, main
from agent_sudo.models import Decision
from agent_sudo.policy import load_default_policy


class UniversalAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = load_default_policy()

    def test_generic_adapter_maps_unknown_tools_to_sensitive(self) -> None:
        request = from_generic_tool_call(
            {
                "actor": "agent-a",
                "agent_type": "generic",
                "source": "user",
                "source_trust": "USER_DIRECT",
                "tool": "unknown_tool",
                "action": "inspect",
                "target": "/home/user/example/project",
                "payload_summary": "Inspect example project",
                "payload_hash": "sha256:example-placeholder",
                "requested_at": "2026-01-01T00:00:00Z",
                "session_id": "session-generic-test",
            }
        )
        result = PermissionGateway(self.policy).evaluate(request, dry_run=True)

        self.assertEqual(request.action, "unknown_tool_call")
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_claude_desktop_file_edit_maps_to_edit_file(self) -> None:
        request = from_claude_desktop_tool_call(
            {
                "actor": "claude-desktop",
                "agent_type": "claude_desktop",
                "source": "user",
                "source_trust": "USER_DIRECT",
                "tool": "filesystem",
                "action": "edit_file",
                "target": "/home/user/example/project/notes.md",
                "payload_summary": "Edit notes",
            }
        )

        self.assertEqual(request.actor, "claude-desktop")
        self.assertEqual(request.action, "edit_file")
        self.assertEqual(request.target, "/home/user/example/project/notes.md")

    def test_mcp_tool_call_maps_correctly(self) -> None:
        request = from_mcp_tool_call(
            {
                "actor": "mcp-client",
                "agent_type": "mcp",
                "source": "user",
                "source_trust": "USER_DIRECT",
                "tool": "shell",
                "action": "run_shell_command",
                "target": "echo hello",
                "payload_summary": "Run command",
            }
        )

        self.assertEqual(request.actor, "mcp-client")
        self.assertEqual(request.tool, "shell")
        self.assertEqual(request.action, "run_shell_command")
        self.assertEqual(request.target, "echo hello")

    def test_openclaw_browser_click_maps_to_browser_click(self) -> None:
        request = from_openclaw_tool_call(
            {
                "actor": "openclaw",
                "agent_type": "openclaw",
                "source": "user",
                "source_trust": "USER_DIRECT",
                "tool": "browser",
                "action": "click",
                "target": "button-1",
                "payload_summary": "Click button",
            }
        )

        self.assertEqual(request.actor, "openclaw")
        self.assertEqual(request.action, "browser_click")
        self.assertEqual(request.target, "button-1")

    def test_generic_run_dry_run_works(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "tool_call.json"
            path.write_text(
                json.dumps(
                    {
                        "actor": "agent-a",
                        "agent_type": "generic",
                        "source": "user",
                        "source_trust": "USER_DIRECT",
                        "tool": "unknown_tool",
                        "action": "inspect",
                        "target": "/home/user/example/project",
                        "payload_summary": "Inspect example project",
                        "payload_hash": "sha256:example-placeholder",
                        "requested_at": "2026-01-01T00:00:00Z",
                        "session_id": "session-generic-test",
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with redirect_stdout(output):
                code = main(["generic-run", str(path), "--dry-run"])

        self.assertEqual(code, 0)
        self.assertIn('"executed": false', output.getvalue())
        self.assertIn('"decision": "REQUIRE_APPROVAL"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
