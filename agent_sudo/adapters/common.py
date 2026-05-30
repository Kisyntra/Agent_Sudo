from __future__ import annotations

import json
from typing import Any

from agent_sudo.builders import AgentActionRequest
from agent_sudo.models import (
    ActionRequest,
    AuthenticationMethod,
    Channel,
    OriginType,
    Provenance,
    TrustLevel,
)


def normalize_tool_call(
    tool_call: dict[str, Any], *, default_actor: str
) -> ActionRequest:
    actor = str(tool_call.get("actor", default_actor))
    source = str(tool_call.get("source", "unknown"))
    provenance = _provenance(tool_call, source)
    source_trust = _source_trust(tool_call, source, provenance)
    tool = _tool_name(tool_call)
    action = _action_name(tool_call)
    params = _params(tool_call)
    normalized = _normalize_token(f"{tool} {action}")
    risk_hints = _risk_hints(tool_call, params)

    if (
        tool == "get_runtime_context"
        or action == "get_runtime_context"
        or normalized.strip() == "get_runtime_context"
    ):
        return ActionRequest(
            actor=actor,
            source=source,
            tool=tool or "get_runtime_context",
            action="get_runtime_context",
            target=_target(tool_call),
            payload_summary=_summary(tool_call, "Get runtime workspace context"),
            risk_hints=risk_hints,
            source_trust=source_trust,
            provenance=provenance,
        )

    if action in {
        "exfiltrate_secrets",
        "disable_audit",
        "bypass_policy",
        "send_tokens",
        "destructive_recursive_delete",
    }:
        return ActionRequest(
            actor=actor,
            source=source,
            tool=tool or "unknown",
            action=action,
            target=_target(tool_call),
            payload_summary=_summary(tool_call, "Blocked native tool call"),
            risk_hints=risk_hints,
            source_trust=source_trust,
            provenance=provenance,
        )

    if _is_shell(normalized):
        return AgentActionRequest.shell_command(
            _first_string(
                params, ["cmd", "command", "shell_command", "target"], fallback=action
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
        )

    if _is_read_file(normalized):
        return AgentActionRequest.file_read(
            _first_string(
                params,
                ["path", "file", "filename", "target"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Read local file"),
        )

    if _is_file_delete(normalized):
        return AgentActionRequest.file_delete(
            _first_string(
                params,
                ["path", "file", "filename", "target"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Delete local file"),
        )

    if _is_file_edit(normalized):
        return AgentActionRequest.file_edit(
            _first_string(
                params,
                ["path", "file", "filename", "target"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Edit local file"),
        )

    if _is_file_write(normalized):
        return AgentActionRequest.file_write(
            _first_string(
                params,
                ["path", "file", "filename", "target"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Write local file"),
        )

    if _is_browser_click(normalized):
        return AgentActionRequest.browser_click(
            _browser_target(params, tool_call),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Click browser element"),
        )

    if _is_send_email(normalized):
        return AgentActionRequest.send_email(
            _first_string(
                params, ["to", "recipient", "target"], fallback=_target(tool_call)
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Send email"),
        )

    if _is_send_message(normalized):
        return AgentActionRequest.send_message(
            _first_string(
                params,
                ["to", "channel", "target", "recipient"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Send message"),
        )

    if _is_auth_edit(normalized):
        return AgentActionRequest.modify_auth(
            _first_string(
                params,
                ["target", "path", "account", "resource"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Modify authentication settings"),
        )

    if _is_cron(normalized):
        return AgentActionRequest.create_cron(
            _first_string(
                params,
                ["target", "schedule", "command", "cmd"],
                fallback=_target(tool_call),
            ),
            actor=actor,
            source=source,
            source_trust=source_trust,
            provenance=provenance,
            summary=_summary(tool_call, "Create scheduled task"),
        )

    return ActionRequest(
        actor=actor,
        source=source,
        tool=tool or "unknown",
        action="unknown_tool_call",
        target=_target(tool_call),
        payload_summary=_summary(tool_call, "Unknown native tool call"),
        risk_hints=risk_hints + ["unknown_tool"],
        source_trust=source_trust,
        provenance=provenance,
    )


def _tool_name(tool_call: dict[str, Any]) -> str:
    return str(
        tool_call.get("tool")
        or tool_call.get("tool_name")
        or tool_call.get("name")
        or tool_call.get("recipient_name")
        or "unknown"
    )


def _action_name(tool_call: dict[str, Any]) -> str:
    return str(
        tool_call.get("action")
        or tool_call.get("operation")
        or tool_call.get("cmd")
        or tool_call.get("command")
        or ""
    )


def _params(tool_call: dict[str, Any]) -> dict[str, Any]:
    for key in ("parameters", "params", "arguments", "input", "kwargs"):
        value = tool_call.get(key)
        if isinstance(value, dict):
            nested = value.get("kwargs")
            if isinstance(nested, dict):
                merged = dict(value)
                merged.update(nested)
                return merged
            return value
    return tool_call


def _first_string(
    params: dict[str, Any], keys: list[str], *, fallback: str = ""
) -> str:
    for key in keys:
        value = params.get(key)
        if value is not None:
            return _stringify(value)
    return fallback


def _target(tool_call: dict[str, Any]) -> str:
    params = _params(tool_call)
    return _first_string(
        params,
        ["target", "path", "file", "filename", "cmd", "command", "url", "selector"],
        fallback=_tool_name(tool_call),
    )


def _summary(tool_call: dict[str, Any], fallback: str) -> str:
    value = (
        tool_call.get("payload_summary")
        or tool_call.get("summary")
        or tool_call.get("description")
    )
    return str(value) if value else fallback


def _risk_hints(tool_call: dict[str, Any], params: dict[str, Any]) -> list[str]:
    value = tool_call.get("risk_hints", params.get("risk_hints", []))
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [value]
    return []


def _source_trust(
    tool_call: dict[str, Any], source: str, provenance: Provenance
) -> TrustLevel:
    raw = tool_call.get("source_trust")
    if isinstance(raw, str):
        return TrustLevel(raw)
    if provenance.origin_type == OriginType.USER_DIRECT:
        return TrustLevel.USER_DIRECT
    if provenance.origin_type == OriginType.AGENT_INTERNAL:
        return TrustLevel.AGENT_INTERNAL
    if provenance.origin_type in {OriginType.EXTERNAL_CONTENT, OriginType.EXTERNAL_API}:
        return TrustLevel.EXTERNAL_CONTENT
    normalized_source = source.lower()
    if normalized_source in {"user", "human", "user_direct"}:
        return TrustLevel.USER_DIRECT
    if any(
        token in normalized_source
        for token in {"web", "email", "document", "external", "slack", "browser"}
    ):
        return TrustLevel.EXTERNAL_CONTENT
    return TrustLevel.UNKNOWN


def _provenance(tool_call: dict[str, Any], source: str) -> Provenance:
    existing = tool_call.get("provenance")
    if isinstance(existing, dict):
        return Provenance.from_dict(existing)
    return Provenance(
        origin_type=_origin_type(tool_call, source),
        channel=_channel(tool_call, source),
        authenticated=bool(tool_call.get("authenticated", False)),
        authentication_method=AuthenticationMethod(
            str(tool_call.get("authentication_method", "unknown"))
        ),
        session_id=str(tool_call.get("session_id", "")),
        request_id=str(tool_call.get("request_id", "")),
        parent_request_id=str(tool_call.get("parent_request_id", "")),
        delegation_chain=[str(item) for item in tool_call.get("delegation_chain", [])],
    )


def _origin_type(tool_call: dict[str, Any], source: str) -> OriginType:
    raw = tool_call.get("origin_type")
    if isinstance(raw, str):
        return OriginType(raw)
    normalized_source = source.lower()
    if normalized_source in {"user", "human", "user_direct"}:
        return OriginType.USER_DIRECT
    if "api" in normalized_source:
        return OriginType.EXTERNAL_API
    if any(
        token in normalized_source
        for token in {"web", "email", "document", "external", "browser"}
    ):
        return OriginType.EXTERNAL_CONTENT
    if "agent" in normalized_source:
        return OriginType.AGENT_INTERNAL
    return OriginType.UNKNOWN


def _channel(tool_call: dict[str, Any], source: str) -> Channel:
    raw = tool_call.get("channel")
    if isinstance(raw, str):
        return Channel(raw)
    normalized_source = source.lower()
    if "cli" in normalized_source or normalized_source in {"user", "human"}:
        return Channel.CLI
    if "desktop" in normalized_source:
        return Channel.DESKTOP_APP
    if "browser" in normalized_source:
        return Channel.BROWSER
    if "email" in normalized_source:
        return Channel.EMAIL
    if "web" in normalized_source:
        return Channel.WEBPAGE
    if "api" in normalized_source:
        return Channel.API
    if "mcp" in normalized_source:
        return Channel.MCP
    return Channel.UNKNOWN


def _browser_target(params: dict[str, Any], tool_call: dict[str, Any]) -> str:
    explicit = _first_string(
        params, ["target", "element", "element_index", "selector", "ref"], fallback=""
    )
    if explicit:
        return explicit
    if "x" in params and "y" in params:
        return f"x={params['x']},y={params['y']}"
    return _target(tool_call)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, sort_keys=True)


def _normalize_token(value: str) -> str:
    return value.lower().replace("-", "_").replace(".", "_").replace(":", "_")


def _is_shell(value: str) -> bool:
    return any(
        token in value
        for token in {"terminal", "shell", "exec_command", "run_shell_command", "bash"}
    )


def _is_read_file(value: str) -> bool:
    return "read_file" in value or "filesystem_read" in value


def _is_file_write(value: str) -> bool:
    return "write_file" in value or "filesystem_write" in value


def _is_file_edit(value: str) -> bool:
    return any(
        token in value
        for token in {
            "edit_file",
            "apply_patch",
            "patch",
            "update_file",
            "replace_file",
        }
    )


def _is_file_delete(value: str) -> bool:
    return "delete_file" in value or "remove_file" in value or "unlink" in value


def _is_browser_click(value: str) -> bool:
    return "browser_click" in value or (
        "click" in value and ("browser" in value or "computer_use" in value)
    )


def _is_send_email(value: str) -> bool:
    return "send_email" in value or ("gmail" in value and "send" in value)


def _is_send_message(value: str) -> bool:
    return "send_message" in value or ("message" in value and "send" in value)


def _is_auth_edit(value: str) -> bool:
    return any(
        token in value
        for token in {"modify_auth", "auth", "credential", "token", "secret"}
    ) and any(verb in value for verb in {"modify", "edit", "write", "update", "set"})


def _is_cron(value: str) -> bool:
    return any(
        token in value for token in {"cron", "cronjob", "create_cron", "scheduled_task"}
    )
