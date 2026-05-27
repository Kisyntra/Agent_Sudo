from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Callable

from agent_sudo.models import ActionRequest, ApprovalResult


CONFIG_PATH = Path.home() / ".agent-sudo" / "config.json"
LOCKOUT_PATH = Path.home() / ".agent-sudo" / "approval_state.json"
PBKDF2_ITERATIONS = 390_000
DEFAULT_MAX_FAILED_ATTEMPTS = 3
DEFAULT_LOCKOUT_SECONDS = 300


class ApprovalProvider:
    def __init__(
        self,
        *,
        config_path: Path = CONFIG_PATH,
        input_func: Callable[[str], str] = input,
        getpass_func: Callable[[str], str] = getpass.getpass,
        stdin_is_tty: Callable[[], bool] | None = None,
        lockout_path: Path = LOCKOUT_PATH,
        max_failed_attempts: int = DEFAULT_MAX_FAILED_ATTEMPTS,
        lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS,
        now_func: Callable[[], float] = time.time,
    ):
        self.config_path = config_path
        self.input_func = input_func
        self.getpass_func = getpass_func
        self.stdin_is_tty = stdin_is_tty or sys.stdin.isatty
        self.lockout_path = lockout_path
        self.max_failed_attempts = max_failed_attempts
        self.lockout_seconds = lockout_seconds
        self.now_func = now_func

    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        if not self.stdin_is_tty():
            return ApprovalResult(
                approved=False,
                method="CLI_CONFIRM",
                reason="approval requires an interactive TTY",
                pending=True,
            )
        answer = self.input_func(_approval_prompt(request)).strip().lower()
        approved = answer in {"y", "yes"}
        return ApprovalResult(
            approved=approved,
            method="CLI_CONFIRM",
            reason="approved by CLI confirmation" if approved else "rejected by CLI confirmation",
        )

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        if not self.stdin_is_tty():
            return ApprovalResult(
                approved=False,
                method="PASSPHRASE_CONFIRM",
                reason="strong approval requires an interactive TTY",
                pending=True,
            )
        config = load_approval_config(self.config_path)
        if config is None:
            return ApprovalResult(
                approved=False,
                method="PASSPHRASE_CONFIRM",
                reason="approval passphrase is not initialized",
            )
        locked_until = self._locked_until()
        now = self.now_func()
        if locked_until > now:
            return ApprovalResult(
                approved=False,
                method="PASSPHRASE_CONFIRM",
                reason=f"approval locked until {int(locked_until)} after failed attempts",
            )
        entered = self.getpass_func(_strong_approval_prompt(request))
        approved = verify_passphrase(entered, config)
        if approved:
            self._reset_lockout_state()
        else:
            failed_attempts, locked_until = self._record_failed_attempt()
            if locked_until > self.now_func():
                return ApprovalResult(
                    approved=False,
                    method="PASSPHRASE_CONFIRM",
                    reason=f"passphrase verification failed; approval locked until {int(locked_until)}",
                )
        return ApprovalResult(
            approved=approved,
            method="PASSPHRASE_CONFIRM",
            reason="passphrase verified" if approved else f"passphrase verification failed ({failed_attempts} failed attempts)",
        )

    def _locked_until(self) -> float:
        state = _load_lockout_state(self.lockout_path)
        locked_until = float(state.get("locked_until", 0))
        if locked_until and locked_until <= self.now_func():
            self._reset_lockout_state()
            return 0.0
        return locked_until

    def _record_failed_attempt(self) -> tuple[int, float]:
        state = _load_lockout_state(self.lockout_path)
        failed_attempts = int(state.get("failed_attempts", 0)) + 1
        locked_until = 0.0
        if failed_attempts >= self.max_failed_attempts:
            locked_until = self.now_func() + self.lockout_seconds
        _write_lockout_state(
            self.lockout_path,
            {"failed_attempts": failed_attempts, "locked_until": locked_until},
        )
        return failed_attempts, locked_until

    def _reset_lockout_state(self) -> None:
        _write_lockout_state(self.lockout_path, {"failed_attempts": 0, "locked_until": 0})


class AutoDenyApprovalProvider(ApprovalProvider):
    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(False, "DENY", "approval disabled")

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(False, "DENY", "strong approval disabled")


def init_approval_config(
    *,
    config_path: Path = CONFIG_PATH,
    pending_approvals_path: Path | None = None,
    delegations_path: Path | None = None,
    audit_log_path: Path | None = None,
    force: bool = False,
    getpass_func: Callable[[str], str] | None = None,
    input_func: Callable[[str], str] | None = None,
) -> None:
    if input_func is None:
        input_func = input
    if getpass_func is None:
        import getpass
        getpass_func = getpass.getpass

    from agent_sudo.delegations import DELEGATIONS_PATH, DelegationStore
    from agent_sudo.pending_approvals import PENDING_APPROVALS_PATH, PendingApprovalStore
    from agent_sudo.audit import AuditLogger

    actual_delegations_path = delegations_path or DELEGATIONS_PATH
    actual_pending_path = pending_approvals_path or PENDING_APPROVALS_PATH

    is_reset = config_path.exists()

    if is_reset and not force:
        print("Resetting the approval passphrase will revoke delegations and cancel pending approvals.")
        answer = input_func("Do you want to proceed? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            raise ValueError("passphrase reset aborted by user")

    first = getpass_func("Create agent-sudo approval passphrase: ")
    second = getpass_func("Confirm agent-sudo approval passphrase: ")
    if not first:
        raise ValueError("passphrase cannot be empty")
    if first != second:
        raise ValueError("passphrases do not match")

    if is_reset:
        revoked_delegations_count = 0
        del_store = DelegationStore(actual_delegations_path)
        try:
            tokens = del_store.list()
        except Exception:
            tokens = []

        if tokens:
            updated_tokens = []
            for token in tokens:
                if not token.revoked:
                    from dataclasses import replace
                    token = replace(token, revoked=True)
                    revoked_delegations_count += 1
                updated_tokens.append(token)
            if revoked_delegations_count > 0:
                del_store.save(updated_tokens)

        canceled_approvals_count = 0
        pending_store = PendingApprovalStore(actual_pending_path)
        try:
            approvals = pending_store.list(update_expired=False)
        except Exception:
            approvals = []

        if approvals:
            from agent_sudo.models import ApprovalStatus
            updated_approvals = []
            for approval in approvals:
                if approval.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
                    from dataclasses import replace
                    approval = replace(approval, status=ApprovalStatus.DENIED, reason="passphrase was reset")
                    canceled_approvals_count += 1
                updated_approvals.append(approval)
            if canceled_approvals_count > 0:
                pending_store.save(updated_approvals)

        if audit_log_path:
            audit_logger = AuditLogger(audit_log_path)
            payload = {
                "revoked_delegations_count": revoked_delegations_count,
                "canceled_pending_approvals_count": canceled_approvals_count,
                "config_path": str(config_path),
            }
            audit_logger.record_event("passphrase_reset", payload)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        config_path.parent.chmod(0o700)
    except PermissionError:
        pass

    config = hash_passphrase(first)
    config_path.write_text(json.dumps(config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    try:
        config_path.chmod(0o600)
    except PermissionError:
        pass


def hash_passphrase(passphrase: str, *, salt: bytes | None = None) -> dict[str, str | int]:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), actual_salt, PBKDF2_ITERATIONS)
    return {
        "approval_hash_algorithm": "pbkdf2_hmac_sha256",
        "approval_hash_iterations": PBKDF2_ITERATIONS,
        "approval_hash_salt": actual_salt.hex(),
        "approval_hash": digest.hex(),
    }


def verify_passphrase(passphrase: str, config: dict[str, object]) -> bool:
    if config.get("approval_hash_algorithm") != "pbkdf2_hmac_sha256":
        return False
    iterations = int(config["approval_hash_iterations"])
    salt = bytes.fromhex(str(config["approval_hash_salt"]))
    expected = str(config["approval_hash"])
    actual = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations).hex()
    return hmac.compare_digest(actual, expected)


def load_approval_config(config_path: Path = CONFIG_PATH) -> dict[str, object] | None:
    if not config_path.exists():
        return None
    return json.loads(config_path.read_text(encoding="utf-8"))


def _load_lockout_state(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"failed_attempts": 0, "locked_until": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"failed_attempts": 0, "locked_until": 0}
    if not isinstance(data, dict):
        return {"failed_attempts": 0, "locked_until": 0}
    return data


def _write_lockout_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except PermissionError:
        pass
    path.write_text(json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except PermissionError:
        pass


def _approval_prompt(request: ActionRequest) -> str:
    return (
        f"Approve SENSITIVE action {request.action!r} by {request.actor!r} "
        f"on {request.target!r}? [y/N] "
    )


def _strong_approval_prompt(request: ActionRequest) -> str:
    return (
        f"Type agent-sudo passphrase to approve CRITICAL action {request.action!r} "
        f"by {request.actor!r} on {request.target!r}: "
    )
