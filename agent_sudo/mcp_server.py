from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, BinaryIO, Iterable

from agent_sudo import __version_label__
from agent_sudo.audit import AuditLogger
from agent_sudo.delegations import DelegationStore
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_gateway import MCPGateway
from agent_sudo.mcp_validation import tool_call_from_jsonrpc
from agent_sudo.models import ActionRequest, Decision
from agent_sudo.pending_approvals import PENDING_APPROVALS_PATH, PendingApprovalStore
from agent_sudo.policy import load_default_policy, load_policy


SERVER_NAME = "agent-sudo-mcp"
PROTOCOL_VERSION = "2025-03-26"


TOOLS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": "Read a local file through agent-sudo policy enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a local file through agent-sudo policy enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write."},
                "content": {"type": "string", "description": "UTF-8 text content."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell_command",
        "description": "Run a narrow local shell command through agent-sudo policy enforcement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command line to evaluate."},
            },
            "required": ["command"],
        },
    },
]


class AgentSudoMCPServer:
    def __init__(self, gateway: PermissionGateway):
        self.gateway = gateway
        self.mcp_gateway = MCPGateway(gateway)

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        if method == "notifications/initialized":
            return None
        request_id = message.get("id")
        try:
            if method == "initialize":
                return _response(request_id, self._initialize_result())
            if method == "tools/list":
                return _response(request_id, {"tools": TOOLS})
            if method == "tools/call":
                return _response(request_id, self._call_tool(message))
            return _error(request_id, -32601, f"method not found: {method}")
        except Exception as exc:
            return _error(request_id, -32603, str(exc))

    def _initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": __version_label__},
        }

    def _call_tool(self, message: dict[str, Any]) -> dict[str, Any]:
        tool_call = tool_call_from_jsonrpc(message)
        execution = self.mcp_gateway.dispatch(tool_call)
        approval_required = execution.gateway_result.decision in {
            Decision.REQUIRE_APPROVAL,
            Decision.REQUIRE_STRONG_APPROVAL,
        }
        transcript = {
            "status": "approval_required" if approval_required else ("executed" if execution.executed else "blocked"),
            "incoming_mcp_request": message,
            "normalized_action_request": execution.request.to_dict(),
            "classification": execution.gateway_result.classification.value,
            "risk": execution.gateway_result.classification.value,
            "approval_decision": execution.gateway_result.decision.value,
            "approval_method": execution.gateway_result.approval_method,
            "approval_request_id": execution.gateway_result.approval_request_id,
            "approval_id": execution.gateway_result.approval_request_id,
            "approval_command": execution.gateway_result.approval_command,
            "expires_at": execution.gateway_result.approval_expires_at,
            "expires_in_seconds": execution.gateway_result.approval_expires_in_seconds,
            "action_summary": _action_summary(execution.request),
            "execution_result": {
                "executed": execution.executed,
                "exit_code": execution.exit_code,
                "stdout": execution.stdout,
                "stderr": execution.stderr,
                "reason": execution.reason,
            },
        }
        is_error = execution.gateway_result.decision != Decision.ALLOW or not execution.executed
        return {
            "content": [
                {
                    "type": "text",
                    "text": _tool_text(execution.executed, execution.stdout, execution.stderr, execution.reason),
                }
            ],
            "structuredContent": transcript,
            "isError": is_error,
        }


def build_server(
    *,
    policy_path: Path | None = None,
    audit_log: Path | None = None,
    delegations_file: Path | None = None,
    pending_approvals_file: Path | None = None,
    approval_ttl_seconds: int | None = None,
) -> AgentSudoMCPServer:
    policy = load_policy(policy_path) if policy_path else load_default_policy()
    audit_logger = AuditLogger(audit_log or Path(".agent-sudo/mcp-audit.jsonl"))
    delegation_store = DelegationStore(delegations_file) if delegations_file else None
    pending_store = PendingApprovalStore(
        pending_approvals_file or PENDING_APPROVALS_PATH,
        audit_logger=audit_logger,
        ttl_seconds=approval_ttl_seconds,
    )
    gateway = PermissionGateway(
        policy,
        audit_logger=audit_logger,
        delegation_store=delegation_store,
        pending_approval_store=pending_store,
    )
    return AgentSudoMCPServer(gateway)


def serve(
    *,
    input_stream: BinaryIO | None = None,
    output_stream: BinaryIO | None = None,
    server: AgentSudoMCPServer | None = None,
) -> int:
    actual_input = input_stream or sys.stdin.buffer
    actual_output = output_stream or sys.stdout.buffer
    actual_server = server or build_server()
    while True:
        message = read_message(actual_input)
        if message is None:
            return 0
        response = actual_server.handle(message)
        if response is not None:
            write_message(actual_output, response)


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    while True:
        line = stream.readline()
        if line == b"":
            return None
        decoded = line.decode("utf-8").strip()
        if not decoded:
            continue
        parsed = json.loads(decoded)
        if not isinstance(parsed, dict):
            raise ValueError("MCP message must be a JSON object")
        return parsed


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    stream.write(body + b"\n")
    stream.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SERVER_NAME)
    parser.add_argument("--version", action="version", version=f"{SERVER_NAME} {__version_label__}")
    parser.add_argument("--policy", type=Path, help="Path to policy YAML")
    parser.add_argument("--audit-log", type=Path, default=Path(".agent-sudo/mcp-audit.jsonl"))
    parser.add_argument("--delegations-file", type=Path)
    parser.add_argument("--pending-approvals-file", type=Path, default=PENDING_APPROVALS_PATH)
    parser.add_argument("--approval-ttl-seconds", type=int, help="Pending approval TTL, clamped to 30-600 seconds")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    server = build_server(
        policy_path=args.policy,
        audit_log=args.audit_log,
        delegations_file=args.delegations_file,
        pending_approvals_file=args.pending_approvals_file,
        approval_ttl_seconds=args.approval_ttl_seconds,
    )
    return serve(server=server)


def _response(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_text(executed: bool, stdout: str, stderr: str, reason: str) -> str:
    if executed:
        return stdout if stdout else reason
    if stderr:
        return f"{reason}: {stderr}"
    return reason


def _action_summary(request: ActionRequest) -> str:
    return f"{request.action} by {request.actor} on {request.target}"


if __name__ == "__main__":
    raise SystemExit(main())
