from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any

from agent_sudo.adapters.mcp import from_mcp_tool_call
from agent_sudo.executors import ExecutionResult
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest, Decision, GatewayResult


DEMO_WRITE_ROOT = Path("/tmp/agent-sudo-demo")
DEMO_SHELL_COMMANDS = {"pwd", "ls", "cat"}


class MCPGateway:
    def __init__(
        self,
        gateway: PermissionGateway,
        *,
        write_root: Path = DEMO_WRITE_ROOT,
        workspace: str | None = None,
    ):
        self.gateway = gateway
        self.write_root = write_root
        self.workspace = workspace

    def dispatch(self, tool_call: dict[str, Any], *, dry_run: bool = False) -> ExecutionResult:
        request = from_mcp_tool_call(tool_call)
        gateway_result = self.gateway.evaluate(request, dry_run=dry_run)
        if dry_run:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason="dry-run: gateway evaluated MCP tool call without executing tool",
            )
        if gateway_result.decision != Decision.ALLOW:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason=gateway_result.reason,
            )
        return self._execute_demo_tool(request, gateway_result, tool_call)

    def _execute_demo_tool(
        self,
        request: ActionRequest,
        gateway_result: GatewayResult,
        tool_call: dict[str, Any],
    ) -> ExecutionResult:
        if request.action == "read_file":
            return self._read_file(request, gateway_result)
        if request.action == "write_file":
            return self._write_file(request, gateway_result, tool_call)
        if request.action == "run_shell_command":
            return self._run_shell_command(request, gateway_result)
        if request.action == "get_runtime_context":
            return self._get_runtime_context(request, gateway_result)
        return ExecutionResult(
            request=request,
            gateway_result=gateway_result,
            executed=False,
            exit_code=None,
            reason=f"demo MCP gateway does not implement action {request.action!r}",
        )

    def _get_runtime_context(self, request: ActionRequest, gateway_result: GatewayResult) -> ExecutionResult:
        from agent_sudo.context import detect_runtime_context
        try:
            ctx = detect_runtime_context(workspace=self.workspace)
            stdout_content = json.dumps(ctx.to_dict(), sort_keys=True)
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=True,
                exit_code=0,
                stdout=stdout_content,
                reason="executed",
            )
        except Exception as exc:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=1,
                stderr=str(exc),
                reason=f"failed to get runtime context: {exc}",
            )

    def _read_file(self, request: ActionRequest, gateway_result: GatewayResult) -> ExecutionResult:
        try:
            content = Path(request.target).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            return ExecutionResult(request, gateway_result, False, None, stderr=str(exc), reason="read failed")
        return ExecutionResult(request, gateway_result, True, 0, stdout=content, reason="executed")

    def _write_file(
        self,
        request: ActionRequest,
        gateway_result: GatewayResult,
        tool_call: dict[str, Any],
    ) -> ExecutionResult:
        target = Path(request.target).expanduser()
        try:
            resolved_root = self.write_root.resolve()
            resolved_target = target.resolve()
        except OSError as exc:
            return ExecutionResult(request, gateway_result, False, None, stderr=str(exc), reason="invalid path")
        if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason="write_file demo tool only writes inside /tmp/agent-sudo-demo",
            )
        content = _content_from_tool_call(tool_call)
        try:
            resolved_target.parent.mkdir(parents=True, exist_ok=True)
            resolved_target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return ExecutionResult(request, gateway_result, False, None, stderr=str(exc), reason="write failed")
        return ExecutionResult(request, gateway_result, True, 0, stdout=str(resolved_target), reason="executed")

    def _run_shell_command(self, request: ActionRequest, gateway_result: GatewayResult) -> ExecutionResult:
        try:
            argv = shlex.split(request.target)
        except ValueError as exc:
            return ExecutionResult(request, gateway_result, False, None, stderr=str(exc), reason="invalid shell syntax")
        if not _demo_shell_allowed(argv):
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason="shell command is outside the MCP demo allowlist",
            )
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        return ExecutionResult(
            request=request,
            gateway_result=gateway_result,
            executed=True,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            reason="executed",
        )


def dispatch_mcp_tool_call(
    tool_call: dict[str, Any],
    gateway: PermissionGateway,
    *,
    dry_run: bool = False,
    workspace: str | None = None,
) -> ExecutionResult:
    return MCPGateway(gateway, workspace=workspace).dispatch(tool_call, dry_run=dry_run)


def _content_from_tool_call(tool_call: dict[str, Any]) -> str:
    params = tool_call.get("parameters") or tool_call.get("params") or tool_call.get("arguments") or tool_call
    if not isinstance(params, dict):
        return ""
    value = params.get("content")
    return str(value) if value is not None else ""


def _demo_shell_allowed(argv: list[str]) -> bool:
    if not argv:
        return False
    if argv[0] in DEMO_SHELL_COMMANDS:
        return True
    return argv[:3] == ["python3", "-m", "unittest"]
