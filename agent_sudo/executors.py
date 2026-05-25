from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import ActionRequest, Classification, Decision, GatewayResult


@dataclass(frozen=True)
class ExecutionResult:
    request: ActionRequest
    gateway_result: GatewayResult
    executed: bool
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    reason: str = ""


class ToolExecutor(Protocol):
    def execute(self, request: ActionRequest) -> ExecutionResult:
        ...

    def dry_run(self, request: ActionRequest) -> ExecutionResult:
        ...


class SafeToolExecutor:
    def __init__(self, gateway: PermissionGateway, inner: ToolExecutor):
        self.gateway = gateway
        self.inner = inner

    def execute(self, request: ActionRequest) -> ExecutionResult:
        gateway_result = self.gateway.evaluate(request)
        if gateway_result.decision != Decision.ALLOW:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason=gateway_result.reason,
            )
        return self.inner.execute_with_gateway_result(request, gateway_result)  # type: ignore[attr-defined]

    def dry_run(self, request: ActionRequest) -> ExecutionResult:
        gateway_result = self.gateway.evaluate(request, dry_run=True)
        return ExecutionResult(
            request=request,
            gateway_result=gateway_result,
            executed=False,
            exit_code=None,
            reason="dry-run: gateway evaluated request without executing tool",
        )


class ShellCommandExecutor:
    def __init__(self, allowed_commands: set[str] | None = None, cwd: Path | None = None):
        self.allowed_commands = allowed_commands or set()
        self.cwd = cwd

    def execute(self, request: ActionRequest) -> ExecutionResult:
        placeholder_gateway_result = GatewayResult(
            request=request,
            classification=Classification.BLOCKED,
            decision=Decision.DENY,
            approval_method="none",
            reason="ShellCommandExecutor must be wrapped by SafeToolExecutor",
        )
        return ExecutionResult(request, placeholder_gateway_result, False, None, reason="missing gateway boundary")

    def dry_run(self, request: ActionRequest) -> ExecutionResult:
        placeholder_gateway_result = GatewayResult(
            request=request,
            classification=Classification.BLOCKED,
            decision=Decision.DENY,
            approval_method="none",
            reason="ShellCommandExecutor dry-run does not execute commands",
            dry_run=True,
        )
        return ExecutionResult(request, placeholder_gateway_result, False, None, reason="dry-run")

    def execute_with_gateway_result(
        self,
        request: ActionRequest,
        gateway_result: GatewayResult,
    ) -> ExecutionResult:
        blocked_reason = _blocked_shell_reason(request.target)
        if blocked_reason is not None:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason=blocked_reason,
            )

        try:
            argv = shlex.split(request.target)
        except ValueError as exc:
            return ExecutionResult(request, gateway_result, False, None, stderr=str(exc), reason="invalid shell syntax")

        if not argv:
            return ExecutionResult(request, gateway_result, False, None, reason="empty command")

        if argv[0] not in self.allowed_commands:
            return ExecutionResult(
                request=request,
                gateway_result=gateway_result,
                executed=False,
                exit_code=None,
                reason=f"command {argv[0]!r} is not allowlisted",
            )

        completed = subprocess.run(
            argv,
            cwd=self.cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return ExecutionResult(
            request=request,
            gateway_result=gateway_result,
            executed=True,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            reason="executed",
        )


def _blocked_shell_reason(command: str) -> str | None:
    lowered = command.lower()
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = []

    if argv and argv[0] == "rm" and any(flag.startswith("-") and "r" in flag and "f" in flag for flag in argv[1:]):
        return "blocked dangerous recursive delete command"

    if argv and argv[0] in {"curl", "wget", "nc", "netcat", "scp", "ssh"}:
        return "blocked network-capable command in local executor"

    if argv and argv[0] == "chmod" and any(_looks_like_auth_path(arg) for arg in argv[1:]):
        return "blocked chmod against auth-related path"

    if "token" in lowered and any(marker in lowered for marker in {"http://", "https://", "curl", "wget", "upload"}):
        return "blocked possible token exfiltration command"

    if any(marker in lowered for marker in {"id_rsa", ".ssh/", "aws_secret_access_key", "private_key"}):
        return "blocked possible credential access command"

    return None


def _looks_like_auth_path(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in {".ssh", ".gnupg", "keychain", "credentials", "token", "auth"})
