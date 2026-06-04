from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.mcp_server import build_server


def _call_msg(name: str, arguments: dict) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


class _ApproveOnWait:
    """Stub sleep that simulates a human approving during the held call."""

    def __init__(self, store):
        self.store = store
        self.calls = 0

    def __call__(self, _seconds: float) -> None:
        self.calls += 1
        for approval in self.store.active_pending():
            self.store.approve(
                approval.approval_request_id, approval_provider=ApprovalProvider()
            )


class InteractiveApprovalsTests(unittest.TestCase):
    def _build(self, tmp: Path, *, interactive: bool):
        return build_server(
            audit_log=tmp / "audit.jsonl",
            pending_approvals_file=tmp / "pending.json",
            interactive_approvals=interactive,
            approval_wait_seconds=30.0,
        )

    def test_block_and_wait_resumes_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            target = tmp / "note.txt"
            target.write_text("hello from disk\n", encoding="utf-8")
            server = self._build(tmp, interactive=True)
            # Approval arrives during the wait; clock held so the window never elapses.
            server._sleep = _ApproveOnWait(server.gateway.pending_approval_store)
            server._monotonic = lambda: 0.0
            server.poll_interval_seconds = 0.0

            result = server._call_tool(_call_msg("read_file", {"path": str(target)}))
            tx = result["structuredContent"]

            self.assertEqual(tx["interactive_wait"]["outcome"], "approved")
            self.assertTrue(tx["execution_result"]["executed"])
            self.assertEqual(tx["approval_decision"], "ALLOW")
            self.assertFalse(result["isError"])
            self.assertIn("hello from disk", result["content"][0]["text"])

    def test_timeout_returns_approval_required_without_executing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            target = tmp / "note.txt"
            target.write_text("data\n", encoding="utf-8")
            server = self._build(tmp, interactive=True)
            clock = iter([0.0, 100.0, 200.0])  # deadline=5; second read blows past it
            server.approval_wait_seconds = 5.0
            server._monotonic = lambda: next(clock)
            slept = []
            server._sleep = lambda s: slept.append(s)

            result = server._call_tool(_call_msg("read_file", {"path": str(target)}))
            tx = result["structuredContent"]

            self.assertEqual(tx["interactive_wait"]["outcome"], "timeout")
            self.assertFalse(tx["execution_result"]["executed"])
            self.assertIn(
                tx["approval_decision"],
                {"REQUIRE_APPROVAL", "REQUIRE_STRONG_APPROVAL"},
            )
            self.assertTrue(result["isError"])
            self.assertEqual(slept, [])  # blew past deadline before sleeping

    def test_flag_off_is_unchanged_no_wait(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            target = tmp / "note.txt"
            target.write_text("data\n", encoding="utf-8")
            server = self._build(tmp, interactive=False)
            # If the wait loop ran, this sleep would raise.
            server._sleep = lambda s: (_ for _ in ()).throw(
                AssertionError("must not wait when flag off")
            )

            result = server._call_tool(_call_msg("read_file", {"path": str(target)}))
            tx = result["structuredContent"]

            self.assertNotIn("interactive_wait", tx)
            self.assertFalse(tx["execution_result"]["executed"])
            self.assertIn(
                tx["approval_decision"],
                {"REQUIRE_APPROVAL", "REQUIRE_STRONG_APPROVAL"},
            )


if __name__ == "__main__":
    unittest.main()
