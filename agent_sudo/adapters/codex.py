from __future__ import annotations

from typing import Any

from agent_sudo.adapters.common import normalize_tool_call
from agent_sudo.executors import ExecutionResult, SafeToolExecutor
from agent_sudo.models import ActionRequest


def from_codex_tool_call(tool_call: dict[str, Any]) -> ActionRequest:
    return normalize_tool_call(tool_call, default_actor="codex")


def execute_codex_tool_call(tool_call: dict[str, Any], executor: SafeToolExecutor) -> ExecutionResult:
    return executor.execute(from_codex_tool_call(tool_call))
