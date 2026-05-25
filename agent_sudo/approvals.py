from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Callable

from agent_sudo.models import ActionRequest, ApprovalResult


CONFIG_PATH = Path.home() / ".agent-sudo" / "config.json"
PBKDF2_ITERATIONS = 390_000


class ApprovalProvider:
    def __init__(
        self,
        *,
        config_path: Path = CONFIG_PATH,
        input_func: Callable[[str], str] = input,
        getpass_func: Callable[[str], str] = getpass.getpass,
        stdin_is_tty: Callable[[], bool] | None = None,
    ):
        self.config_path = config_path
        self.input_func = input_func
        self.getpass_func = getpass_func
        self.stdin_is_tty = stdin_is_tty or sys.stdin.isatty

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
        entered = self.getpass_func(_strong_approval_prompt(request))
        approved = verify_passphrase(entered, config)
        return ApprovalResult(
            approved=approved,
            method="PASSPHRASE_CONFIRM",
            reason="passphrase verified" if approved else "passphrase verification failed",
        )


class AutoDenyApprovalProvider(ApprovalProvider):
    def approve_sensitive(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(False, "DENY", "approval disabled")

    def approve_critical(self, request: ActionRequest) -> ApprovalResult:
        return ApprovalResult(False, "DENY", "strong approval disabled")


def init_approval_config(
    *,
    config_path: Path = CONFIG_PATH,
    getpass_func: Callable[[str], str] = getpass.getpass,
) -> None:
    first = getpass_func("Create agent-sudo approval passphrase: ")
    second = getpass_func("Confirm agent-sudo approval passphrase: ")
    if not first:
        raise ValueError("passphrase cannot be empty")
    if first != second:
        raise ValueError("passphrases do not match")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.chmod(0o700)
    config = hash_passphrase(first)
    config_path.write_text(json.dumps(config, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    config_path.chmod(0o600)


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
