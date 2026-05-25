from __future__ import annotations

import fnmatch
import json
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_sudo.models import ActionRequest, Classification, DelegationToken


DELEGATIONS_PATH = Path.home() / ".agent-sudo" / "delegations.json"


class DelegationStore:
    def __init__(self, path: Path = DELEGATIONS_PATH):
        self.path = path

    def create(
        self,
        *,
        actor: str,
        allowed_actions: list[str],
        allowed_paths: list[str],
        denied_actions: list[str] | None = None,
        ttl_seconds: int = 7200,
        max_uses: int = 1,
        reason: str = "",
        critical: bool = False,
    ) -> DelegationToken:
        now = datetime.now(timezone.utc)
        token = DelegationToken.create(
            token_id=str(uuid.uuid4()),
            actor=actor,
            allowed_actions=allowed_actions,
            allowed_paths=allowed_paths,
            denied_actions=denied_actions or [],
            expires_at=now + timedelta(seconds=ttl_seconds),
            max_uses=max_uses,
            created_at=now,
            reason=reason,
            critical=critical,
        )
        tokens = self.list()
        tokens.append(token)
        self.save(tokens)
        return token

    def list(self) -> list[DelegationToken]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("delegations file must contain a JSON list")
        return [DelegationToken.from_dict(item) for item in raw]

    def save(self, tokens: list[DelegationToken]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self.path.parent, 0o700)
        self.path.write_text(
            json.dumps([token.to_dict() for token in tokens], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _chmod_best_effort(self.path, 0o600)

    def revoke(self, token_id: str) -> DelegationToken | None:
        tokens = self.list()
        updated: list[DelegationToken] = []
        revoked: DelegationToken | None = None
        for token in tokens:
            if token.token_id == token_id:
                token = replace(token, revoked=True)
                revoked = token
            updated.append(token)
        self.save(updated)
        return revoked

    def authorize(
        self,
        request: ActionRequest,
        *,
        classification: Classification,
        consume: bool = True,
    ) -> tuple[bool | None, str, str]:
        tokens = self.list()
        candidates = [
            token
            for token in tokens
            if request.action in token.allowed_actions or request.action in token.denied_actions
        ]
        if not candidates:
            return None, "no delegation applies", "none"

        matching_scope = [
            token
            for token in candidates
            if token.actor == request.actor and _path_matches(request.target, token.allowed_paths)
        ]

        if not matching_scope:
            return False, "delegation scope mismatch", "DELEGATION"

        for token in matching_scope:
            allowed, reason = _token_allows(token, request, classification)
            if allowed is None:
                return None, reason, "DELEGATION"
            if not allowed:
                return False, reason, "DELEGATION"
            if consume:
                self._increment_usage(token.token_id)
            return True, f"delegated by {token.token_id}: {token.reason}", "DELEGATION"

        return False, "delegation denied", "DELEGATION"

    def _increment_usage(self, token_id: str) -> None:
        tokens = self.list()
        updated = [replace(token, uses=token.uses + 1) if token.token_id == token_id else token for token in tokens]
        self.save(updated)


def _token_allows(
    token: DelegationToken,
    request: ActionRequest,
    classification: Classification,
) -> tuple[bool | None, str]:
    now = datetime.now(timezone.utc)
    if token.revoked:
        return False, "delegation token is revoked"
    if _parse_datetime(token.expires_at) <= now:
        return False, "delegation token is expired"
    if token.uses >= token.max_uses:
        return False, "delegation token is exhausted"
    if request.action in token.denied_actions:
        return False, "delegation token denies this action"
    if request.action not in token.allowed_actions:
        return False, "delegation token does not allow this action"
    if classification == Classification.CRITICAL and not token.critical:
        return None, "critical action requires strong approval unless delegation is critical=true"
    return True, "delegation matched"


def _path_matches(target: str, allowed_paths: list[str]) -> bool:
    if "*" in allowed_paths:
        return True
    normalized_target = str(Path(target).expanduser()).replace("\\", "/")
    for allowed_path in allowed_paths:
        normalized_allowed = str(Path(allowed_path).expanduser()).replace("\\", "/")
        if fnmatch.fnmatch(normalized_target, normalized_allowed):
            return True
        if normalized_target == normalized_allowed:
            return True
        if normalized_target.startswith(normalized_allowed.rstrip("/") + "/"):
            return True
    return False


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        pass
