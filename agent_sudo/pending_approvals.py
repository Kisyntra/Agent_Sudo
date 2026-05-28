from __future__ import annotations

import json
import os
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from agent_sudo.approvals import ApprovalProvider
from agent_sudo.audit import AuditLogger
from agent_sudo.models import (
    ActionRequest,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    Classification,
    Decision,
)


PENDING_APPROVALS_PATH = Path.home() / ".agent-sudo" / "pending_approvals.json"
APPROVAL_TTL_ENV = "AGENT_SUDO_APPROVAL_TTL_SECONDS"
DEFAULT_APPROVAL_TTL_SECONDS = 120
MIN_APPROVAL_TTL_SECONDS = 30
MAX_APPROVAL_TTL_SECONDS = 600


class PendingApprovalStore:
    def __init__(
        self,
        path: Path = PENDING_APPROVALS_PATH,
        *,
        audit_logger: AuditLogger | None = None,
        ttl_seconds: int | None = None,
        now_func: Callable[[], datetime] | None = None,
        notify: bool | None = None,
    ):
        self.path = path
        self.audit_logger = audit_logger
        self.ttl_seconds = resolve_approval_ttl_seconds(ttl_seconds)
        self.now_func = now_func or (lambda: datetime.now(timezone.utc))
        self.notify = notify if notify is not None else (os.environ.get("AGENT_SUDO_NOTIFY") == "1")

    def create(
        self,
        *,
        action_request: ActionRequest,
        classification: Classification,
        decision: Decision,
        required_approval_method: str,
        reason: str,
    ) -> ApprovalRequest:
        now = self._now()
        approval = ApprovalRequest(
            approval_request_id=str(uuid.uuid4()),
            action_request=action_request,
            classification=classification,
            decision=decision,
            required_approval_method=required_approval_method,
            created_at=_format_time(now),
            expires_at=_format_time(now + timedelta(seconds=self.ttl_seconds)),
            status=ApprovalStatus.PENDING,
            reason=reason,
        )
        approvals = self.list(update_expired=False)
        approvals.append(approval)
        self.save(approvals)
        self._record_state("approval_created", approval)

        if self.notify:
            try:
                import sys
                from agent_sudo.notifications import send_approval_notification
                send_approval_notification(approval)
            except Exception as exc:
                import sys
                sys.stderr.write(f"Warning: failed to send desktop notification: {exc}\n")

        return approval

    def list(self, *, update_expired: bool = True) -> list[ApprovalRequest]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("pending approvals file must contain a JSON list")
        approvals = [ApprovalRequest.from_dict(item) for item in raw]
        return self._expire_stale(approvals) if update_expired else approvals

    def save(self, approvals: list[ApprovalRequest]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self.path.parent, 0o700)
        self.path.write_text(
            json.dumps([approval.to_dict() for approval in approvals], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _chmod_best_effort(self.path, 0o600)

    def find_matching(self, request: ActionRequest) -> ApprovalRequest | None:
        fingerprint = _request_fingerprint(request)
        matching = [
            approval
            for approval in self.list()
            if _request_fingerprint(approval.action_request) == fingerprint
            and approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}
        ]
        return matching[-1] if matching else None

    def active_pending(self) -> list[ApprovalRequest]:
        return [approval for approval in self.list() if approval.status == ApprovalStatus.PENDING]

    def approve(
        self,
        approval_request_id: str,
        *,
        approval_provider: ApprovalProvider,
    ) -> tuple[ApprovalRequest | None, ApprovalResult]:
        approvals = self.list()
        updated: list[ApprovalRequest] = []
        target: ApprovalRequest | None = None
        result = ApprovalResult(False, "APPROVAL_STORE", "approval request not found")
        for approval in approvals:
            if approval.approval_request_id != approval_request_id:
                updated.append(approval)
                continue
            target = approval
            if approval.status != ApprovalStatus.PENDING:
                result = ApprovalResult(False, "APPROVAL_STORE", f"approval request is {approval.status.value}")
                updated.append(approval)
                continue
            if self._is_expired(approval):
                expired = replace(approval, status=ApprovalStatus.EXPIRED, reason="approval request expired")
                result = ApprovalResult(False, "APPROVAL_STORE", "approval request expired")
                updated.append(expired)
                target = expired
                self._record_state("approval_expired", expired)
                continue
            if approval.decision == Decision.REQUIRE_STRONG_APPROVAL:
                result = approval_provider.approve_critical(approval.action_request)
                if not result.approved or result.pending:
                    updated.append(approval)
                    self._record_attempt("approval_approve_failed", approval, result)
                    continue
            else:
                result = ApprovalResult(True, "CLI_CONFIRM", "approval request approved")
            approved = replace(approval, status=ApprovalStatus.APPROVED, reason=result.reason)
            updated.append(approved)
            target = approved
            self._record_state("approval_approved", approved)
        self.save(updated)
        return target, result

    def deny(self, approval_request_id: str, *, reason: str = "approval request denied") -> ApprovalRequest | None:
        approvals = self.list()
        updated: list[ApprovalRequest] = []
        denied: ApprovalRequest | None = None
        for approval in approvals:
            if approval.approval_request_id == approval_request_id:
                approval = replace(approval, status=ApprovalStatus.DENIED, reason=reason)
                denied = approval
                self._record_state("approval_denied", approval)
            updated.append(approval)
        self.save(updated)
        return denied

    def consume_matching(self, request: ActionRequest) -> ApprovalRequest | None:
        approvals = self.list()
        updated: list[ApprovalRequest] = []
        consumed: ApprovalRequest | None = None
        fingerprint = _request_fingerprint(request)
        for approval in approvals:
            if consumed is None and approval.status == ApprovalStatus.APPROVED:
                if _request_fingerprint(approval.action_request) == fingerprint:
                    if self._is_expired(approval):
                        approval = replace(approval, status=ApprovalStatus.EXPIRED, reason="approval request expired")
                        self._record_state("approval_expired", approval)
                    else:
                        approval = replace(approval, status=ApprovalStatus.USED, reason="approval request used")
                        consumed = approval
                        self._record_state("approval_used", approval)
            updated.append(approval)
        if consumed is not None:
            self.save(updated)
        return consumed

    def _expire_stale(self, approvals: list[ApprovalRequest]) -> list[ApprovalRequest]:
        changed = False
        updated: list[ApprovalRequest] = []
        for approval in approvals:
            if approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED} and self._is_expired(approval):
                approval = replace(approval, status=ApprovalStatus.EXPIRED, reason="approval request expired")
                changed = True
                self._record_state("approval_expired", approval)
            updated.append(approval)
        if changed:
            self.save(updated)
        return updated

    def _record_state(self, event_type: str, approval: ApprovalRequest) -> None:
        if self.audit_logger is not None:
            self.audit_logger.record_event(event_type, {"approval_request": approval.to_dict()})

    def _record_attempt(self, event_type: str, approval: ApprovalRequest, result: ApprovalResult) -> None:
        if self.audit_logger is not None:
            self.audit_logger.record_event(
                event_type,
                {
                    "approval_request": approval.to_dict(),
                    "approval_result": result.to_dict(),
                },
            )

    def _is_expired(self, approval: ApprovalRequest) -> bool:
        return _parse_time(approval.expires_at) <= self._now()

    def _now(self) -> datetime:
        value = self.now_func()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def resolve_approval_ttl_seconds(value: int | str | None = None) -> int:
    raw_value: int | str | None = value
    if raw_value is None:
        raw_value = os.environ.get(APPROVAL_TTL_ENV)
    if raw_value is None or raw_value == "":
        ttl = DEFAULT_APPROVAL_TTL_SECONDS
    else:
        try:
            ttl = int(raw_value)
        except (TypeError, ValueError):
            ttl = DEFAULT_APPROVAL_TTL_SECONDS
    return min(MAX_APPROVAL_TTL_SECONDS, max(MIN_APPROVAL_TTL_SECONDS, ttl))


def resolve_approval_identifier(identifier: str, approvals: list[ApprovalRequest]) -> str | None:
    if identifier.isdecimal():
        index = int(identifier)
        active = [approval for approval in approvals if approval.status == ApprovalStatus.PENDING]
        if 1 <= index <= len(active):
            return active[index - 1].approval_request_id
    for approval in approvals:
        if approval.approval_request_id == identifier:
            return approval.approval_request_id
    return None


def format_pending_approvals(approvals: list[ApprovalRequest], *, now: datetime | None = None) -> str:
    active = [approval for approval in approvals if approval.status == ApprovalStatus.PENDING]
    if not active:
        return "No active pending approvals."
    actual_now = now or datetime.now(timezone.utc)
    if actual_now.tzinfo is None:
        actual_now = actual_now.replace(tzinfo=timezone.utc)
    rows = ["#  approval_id  action             actor       risk      age  expires"]
    for index, approval in enumerate(active, start=1):
        request = approval.action_request
        rows.append(
            "  ".join(
                [
                    str(index),
                    approval.approval_request_id,
                    _clip(request.action, 18),
                    _clip(request.actor, 10),
                    approval.classification.value,
                    _duration(max(0, int((actual_now - _parse_time(approval.created_at)).total_seconds()))),
                    _duration(max(0, int((_parse_time(approval.expires_at) - actual_now).total_seconds()))),
                ]
            )
        )
    return "\n".join(rows)


def expires_in_seconds(approval: ApprovalRequest, *, now: datetime | None = None) -> int:
    actual_now = now or datetime.now(timezone.utc)
    if actual_now.tzinfo is None:
        actual_now = actual_now.replace(tzinfo=timezone.utc)
    return max(0, int((_parse_time(approval.expires_at) - actual_now.astimezone(timezone.utc)).total_seconds()))


def approval_command(approval_request_id: str) -> str:
    return f"agent-sudo approve {approval_request_id}"


def request_fingerprint(request: ActionRequest) -> str:
    return _request_fingerprint(request)


def _request_fingerprint(request: ActionRequest) -> str:
    data = request.to_dict()
    provenance = data.get("provenance")
    if isinstance(provenance, dict):
        provenance = dict(provenance)
        provenance["request_id"] = ""
        provenance["parent_request_id"] = ""
        data["provenance"] = provenance
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _format_time(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        pass


def _clip(value: str, width: int) -> str:
    return value if len(value) <= width else value[: max(0, width - 1)] + "."


def _duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{remaining:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"
