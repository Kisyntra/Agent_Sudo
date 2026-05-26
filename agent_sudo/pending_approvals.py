from __future__ import annotations

import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
DEFAULT_APPROVAL_TTL_SECONDS = 900


class PendingApprovalStore:
    def __init__(
        self,
        path: Path = PENDING_APPROVALS_PATH,
        *,
        audit_logger: AuditLogger | None = None,
        ttl_seconds: int = DEFAULT_APPROVAL_TTL_SECONDS,
    ):
        self.path = path
        self.audit_logger = audit_logger
        self.ttl_seconds = ttl_seconds

    def create(
        self,
        *,
        action_request: ActionRequest,
        classification: Classification,
        decision: Decision,
        required_approval_method: str,
        reason: str,
    ) -> ApprovalRequest:
        now = datetime.now(timezone.utc)
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
        ]
        return matching[-1] if matching else None

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
            if _is_expired(approval):
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
                    if _is_expired(approval):
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
            if approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED} and _is_expired(approval):
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


def _is_expired(approval: ApprovalRequest) -> bool:
    return _parse_time(approval.expires_at) <= datetime.now(timezone.utc)


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        pass
