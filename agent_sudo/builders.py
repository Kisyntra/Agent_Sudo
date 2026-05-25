from __future__ import annotations

from agent_sudo.models import ActionRequest, Provenance, TrustLevel


def _trust(value: TrustLevel | str) -> TrustLevel:
    if isinstance(value, TrustLevel):
        return value
    return TrustLevel(value)


class AgentActionRequest:
    @staticmethod
    def shell_command(
        command: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        risk_hints: list[str] | None = None,
    ) -> ActionRequest:
        return ActionRequest(
            actor=actor,
            source=source,
            tool="shell",
            action="run_shell_command",
            target=command,
            payload_summary=f"Run shell command: {command}",
            risk_hints=risk_hints or ["shell"],
            source_trust=_trust(source_trust),
            provenance=provenance or Provenance(),
        )

    @staticmethod
    def file_write(
        path: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Write local file",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "filesystem",
            "write_file",
            path,
            summary,
            ["writes_local_file"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def file_edit(
        path: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Edit local file",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "filesystem",
            "edit_file",
            path,
            summary,
            ["writes_local_file"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def file_delete(
        path: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Delete local file",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "filesystem",
            "delete_file",
            path,
            summary,
            ["destructive"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def file_read(
        path: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Read local file",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "filesystem",
            "read_file",
            path,
            summary,
            [],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def browser_click(
        target: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Click browser element",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "browser",
            "browser_click",
            target,
            summary,
            ["browser_action"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def send_message(
        target: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Send message",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "messaging",
            "send_message",
            target,
            summary,
            ["external_side_effect"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def send_email(
        target: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Send email",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "email",
            "send_email",
            target,
            summary,
            ["email_send"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def modify_auth(
        target: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Modify authentication settings",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "auth",
            "modify_auth",
            target,
            summary,
            ["auth"],
            _trust(source_trust),
            provenance or Provenance(),
        )

    @staticmethod
    def create_cron(
        target: str,
        *,
        actor: str = "codex",
        source: str = "user",
        source_trust: TrustLevel | str = TrustLevel.USER_DIRECT,
        provenance: Provenance | None = None,
        summary: str = "Create scheduled task",
    ) -> ActionRequest:
        return ActionRequest(
            actor,
            source,
            "scheduler",
            "create_cron",
            target,
            summary,
            ["scheduled_task"],
            _trust(source_trust),
            provenance or Provenance(),
        )
