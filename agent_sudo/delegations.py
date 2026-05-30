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
            json.dumps([token.to_dict() for token in tokens], indent=2, sort_keys=True)
            + "\n",
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
        if not tokens:
            return None, "no delegation applies", "none"

        now = datetime.now(timezone.utc)
        evaluated = []
        for token in tokens:
            mismatches = []

            # 1. token revoked
            if token.revoked:
                mismatches.append("token revoked")

            # 2. token expired
            if _parse_datetime(token.expires_at) <= now:
                mismatches.append("token expired")

            # 3. token exhausted
            if token.uses >= token.max_uses:
                mismatches.append("token exhausted")

            # 4. denied action
            if request.action in token.denied_actions:
                mismatches.append(f"denied action: '{request.action}'")

            # 5. actor mismatch
            if token.actor != request.actor:
                mismatches.append(
                    f"actor mismatch: expected actor '{token.actor}', actual actor '{request.actor}'"
                )

            # 6. action mismatch
            if (
                request.action not in token.allowed_actions
                and request.action not in token.denied_actions
            ):
                mismatches.append(
                    f"action mismatch: expected action in {token.allowed_actions}, actual action '{request.action}'"
                )

            # 7. path mismatch
            if not _path_matches(request.target, token.allowed_paths):
                mismatches.append(
                    f"path mismatch: expected path scope in {token.allowed_paths}, actual target '{request.target}'"
                )

            # 8. critical flag missing
            if classification == Classification.CRITICAL and not token.critical:
                mismatches.append("critical flag missing")

            evaluated.append((token, mismatches))

        # Check if any token has 0 mismatches
        for token, mismatches in evaluated:
            if not mismatches:
                if consume:
                    self._increment_usage(token.token_id)
                return (
                    True,
                    f"delegated by {token.token_id}: {token.reason}",
                    "DELEGATION",
                )

        # Check if any token has only "critical flag missing" as mismatch
        for token, mismatches in evaluated:
            if mismatches == ["critical flag missing"]:
                reason = f"delegation token {token.token_id} mismatched: critical flag missing"
                return None, reason, "DELEGATION"

        # Build detailed diagnostics for all tokens
        diagnostics = []
        for token, mismatches in evaluated:
            mismatches_str = ", ".join(mismatches)
            diagnostics.append(
                f"delegation token {token.token_id} mismatched: {mismatches_str}"
            )

        reason = "; ".join(diagnostics)
        return False, reason, "DELEGATION"

    def _increment_usage(self, token_id: str) -> None:
        tokens = self.list()
        updated = [
            replace(token, uses=token.uses + 1) if token.token_id == token_id else token
            for token in tokens
        ]
        self.save(updated)


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
