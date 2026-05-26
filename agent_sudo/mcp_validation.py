from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway
from agent_sudo.mcp_gateway import MCPGateway
from agent_sudo.models import GatewayResult
from agent_sudo.policy import Policy


def discover_hermes_mcp() -> dict[str, Any]:
    hermes = shutil.which("hermes")
    cua_driver = shutil.which("cua-driver")
    result: dict[str, Any] = {
        "implementation": "hermes",
        "hermes_available": bool(hermes),
        "cua_driver_available": bool(cua_driver),
        "servers": [],
        "notes": [],
    }
    if hermes:
        completed = subprocess.run([hermes, "mcp", "list"], capture_output=True, text=True, check=False)
        result["hermes_mcp_list_exit_code"] = completed.returncode
        result["hermes_mcp_list"] = _redact_user_paths(completed.stdout.strip())
    if cua_driver:
        completed = subprocess.run([cua_driver, "list-tools"], capture_output=True, text=True, check=False)
        result["servers"].append(
            {
                "name": "cua-driver",
                "transport": "stdio",
                "tool_sample": completed.stdout.splitlines()[:8],
            }
        )
        result["notes"].append("cua-driver is a real Hermes-configured MCP server, but it does not expose file or shell tools.")
    return result


def tool_call_from_jsonrpc(message: dict[str, Any]) -> dict[str, Any]:
    params = message.get("params", {})
    if not isinstance(params, dict):
        raise ValueError("MCP tools/call params must be an object")
    name = str(params.get("name", "unknown_tool"))
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    target = _target_for(name, arguments)
    return {
        "actor": str(message.get("actor", "mcp-client")),
        "agent_type": "mcp",
        "source": str(message.get("source", "user")),
        "source_trust": str(message.get("source_trust", "USER_DIRECT")),
        "tool": _tool_for(name),
        "action": name,
        "target": target,
        "parameters": arguments,
        "payload_summary": str(params.get("summary", f"MCP tools/call {name}")),
        "session_id": str(message.get("session_id", "session-mcp-validation")),
        "request_id": str(message.get("id", "")),
    }


def run_jsonrpc_case(
    message: dict[str, Any],
    *,
    policy: Policy,
    audit_path: Path,
    gateway: PermissionGateway | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    actual_gateway = gateway or PermissionGateway(policy, audit_logger=AuditLogger(audit_path))
    mcp_gateway = MCPGateway(actual_gateway)
    incoming = message
    normalized = tool_call_from_jsonrpc(incoming)
    execution = mcp_gateway.dispatch(normalized, dry_run=dry_run)
    approval_required = execution.gateway_result.decision.name.startswith("REQUIRE_")
    return {
        "status": "approval_required" if approval_required else ("executed" if execution.executed else "blocked"),
        "incoming_mcp_request": incoming,
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
        "action_summary": f"{execution.request.action} by {execution.request.actor} on {execution.request.target}",
        "execution_result": {
            "executed": execution.executed,
            "exit_code": execution.exit_code,
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "reason": execution.reason,
        },
        "audit_entry": _last_audit_entry(audit_path),
    }


def jsonrpc_tool_call(case_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": case_id,
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments,
            "summary": f"Validation case {case_id}",
        },
    }


def _target_for(name: str, arguments: dict[str, Any]) -> str:
    if name == "run_shell_command":
        return str(arguments.get("command", arguments.get("cmd", "")))
    return str(arguments.get("path", arguments.get("target", name)))


def _tool_for(name: str) -> str:
    if name == "run_shell_command":
        return "shell"
    if name in {"read_file", "write_file", "edit_file", "delete_file"}:
        return "filesystem"
    return "mcp"


def _last_audit_entry(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        return None
    return json.loads(lines[-1])


def _redact_user_paths(text: str) -> str:
    home = str(Path.home())
    return text.replace(home, "~")
