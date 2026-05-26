from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MCPServerSubprocessTests(unittest.TestCase):
    def test_agent_sudo_mcp_initialize_list_read_and_blocked_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            audit_path = tmp_path / "mcp-audit.jsonl"
            read_path = tmp_path / "read.txt"
            read_path.write_text("server read ok\n", encoding="utf-8")

            process = subprocess.Popen(
                [str(ROOT / "agent-sudo-mcp"), "--audit-log", str(audit_path)],
                cwd=ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                initialize = _request(
                    process,
                    {
                        "jsonrpc": "2.0",
                        "id": "init",
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-03-26",
                            "capabilities": {},
                            "clientInfo": {"name": "agent-sudo-test-client", "version": "v0.2.0-beta"},
                        },
                    },
                )
                tools = _request(process, {"jsonrpc": "2.0", "id": "tools", "method": "tools/list"})
                read_result = _request(
                    process,
                    {
                        "jsonrpc": "2.0",
                        "id": "read",
                        "method": "tools/call",
                        "params": {"name": "read_file", "arguments": {"path": str(read_path)}},
                    },
                )
                blocked_shell = _request(
                    process,
                    {
                        "jsonrpc": "2.0",
                        "id": "blocked-shell",
                        "method": "tools/call",
                        "params": {"name": "run_shell_command", "arguments": {"command": "rm -rf /"}},
                    },
                )
                audit_entries = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
            finally:
                if process.stdin:
                    process.stdin.close()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

        self.assertEqual(initialize["result"]["serverInfo"]["name"], "agent-sudo-mcp")
        self.assertEqual(initialize["result"]["serverInfo"]["version"], "v0.3.3-beta")
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertEqual(tool_names, {"read_file", "write_file", "run_shell_command"})

        read_payload = read_result["result"]
        self.assertFalse(read_payload.get("isError", False))
        self.assertEqual(read_payload["structuredContent"]["classification"], "SAFE")
        self.assertEqual(read_payload["structuredContent"]["approval_decision"], "ALLOW")
        self.assertTrue(read_payload["structuredContent"]["execution_result"]["executed"])
        self.assertEqual(read_payload["content"][0]["text"], "server read ok\n")

        blocked_payload = blocked_shell["result"]
        self.assertTrue(blocked_payload["isError"])
        self.assertEqual(blocked_payload["structuredContent"]["classification"], "BLOCKED")
        self.assertEqual(blocked_payload["structuredContent"]["approval_decision"], "DENY")
        self.assertFalse(blocked_payload["structuredContent"]["execution_result"]["executed"])

        self.assertEqual([entry["decision"] for entry in audit_entries], ["ALLOW", "DENY"])
        self.assertEqual(audit_entries[0]["request"]["action"], "read_file")
        self.assertEqual(audit_entries[1]["request"]["action"], "run_shell_command")

    def test_read_message_newline_delimited(self) -> None:
        import io
        from agent_sudo.mcp_server import read_message, write_message

        input_data = (
            b'{"jsonrpc":"2.0","id":1,"method":"foo"}\n'
            b'\n'
            b'{"jsonrpc":"2.0","id":2,"method":"bar"}\n'
        )
        stream = io.BytesIO(input_data)
        msg1 = read_message(stream)
        msg2 = read_message(stream)
        msg3 = read_message(stream)

        self.assertIsNotNone(msg1)
        self.assertEqual(msg1["id"], 1)
        self.assertEqual(msg1["method"], "foo")

        self.assertIsNotNone(msg2)
        self.assertEqual(msg2["id"], 2)
        self.assertEqual(msg2["method"], "bar")

        self.assertIsNone(msg3)

        out_stream = io.BytesIO()
        write_message(out_stream, {"jsonrpc": "2.0", "id": 3, "result": "ok"})
        self.assertEqual(out_stream.getvalue(), b'{"id":3,"jsonrpc":"2.0","result":"ok"}\n')


def _request(process: subprocess.Popen[bytes], message: dict[str, object]) -> dict[str, object]:
    if process.stdin is None or process.stdout is None:
        raise AssertionError("MCP subprocess pipes were not opened")
    _write_message(process.stdin, message)
    response = _read_message(process.stdout)
    if response is None:
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        raise AssertionError(f"MCP subprocess closed without response: {stderr}")
    return response


def _write_message(stream: object, message: dict[str, object]) -> None:
    body = json.dumps(message, separators=(",", ":")).encode("utf-8")
    stream.write(body + b"\n")
    stream.flush()


def _read_message(stream: object) -> dict[str, object] | None:
    line = stream.readline()
    if not line:
        return None
    return json.loads(line.decode("utf-8"))


if __name__ == "__main__":
    sys.exit(unittest.main())
