from __future__ import annotations

from typing import Any

from agent_sudo.adapters.common import normalize_tool_call
from agent_sudo.executors import ExecutionResult, SafeToolExecutor
from agent_sudo.models import ActionRequest


def from_claude_desktop_tool_call(tool_call: dict[str, Any]) -> ActionRequest:
    return normalize_tool_call(tool_call, default_actor="claude-desktop")


def execute_claude_desktop_tool_call(tool_call: dict[str, Any], executor: SafeToolExecutor) -> ExecutionResult:
    return executor.execute(from_claude_desktop_tool_call(tool_call))
