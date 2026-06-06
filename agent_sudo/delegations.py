from __future__ import annotations

import fnmatch
import json
import os
import tempfile
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_sudo._locking import (
    DEFAULT_LOCK_TIMEOUT,
    LockTimeout,
    file_lock,
    fsync_dir,
)
from agent_sudo.models import ActionRequest, Classification, DelegationToken


# Environment variable that lets a runtime (e.g. Hermes) point the CLI and the
# embedded engine at a shared delegation store without passing --delegations-file
# on every command.
DELEGATIONS_PATH_ENV = "AGENT_SUDO_DELEGATIONS_FILE"

# Backwards-compatible static fallback used when DELEGATIONS_PATH_ENV is unset.
# Prefer default_delegations_path() for resolution so the environment is read at
# use-time rather than import-time.
DELEGATIONS_PATH = Path.home() / ".agent-sudo" / "delegations.json"


def default_delegations_path() -> Path:
    """Resolve the default delegation store at call time.

    Honors ``AGENT_SUDO_DELEGATIONS_FILE`` so the CLI and integrations converge
    on one store; falls back to ``~/.agent-sudo/delegations.json`` when unset.
    An explicit ``DelegationStore(path=...)`` always overrides this.
    """
    env = os.environ.get(DELEGATIONS_PATH_ENV)
    if env:
        return Path(env).expanduser()
    return DELEGATIONS_PATH


class DelegationStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    ):
        self.path = path if path is not None else default_delegations_path()
        self.lock_timeout = lock_timeout

    @property
    def _lock_path(self) -> Path:
        return Path(str(self.path) + ".lock")

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
        with file_lock(self._lock_path, self.lock_timeout):
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
        # Atomic publish: write a temp file in the same directory, fsync it, then
        # os.replace over the target so a reader/crash never sees a partial file.
        # Format is byte-identical to the previous write_text output.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self.path.parent, 0o700)
        data = (
            json.dumps([token.to_dict() for token in tokens], indent=2, sort_keys=True)
            + "\n"
        )
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".delegations-", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.path)
            _chmod_best_effort(self.path, 0o600)
            fsync_dir(self.path.parent)
        except BaseException:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            raise

    def revoke(self, token_id: str) -> DelegationToken | None:
        with file_lock(self._lock_path, self.lock_timeout):
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
        if not consume:
            # Read-only evaluation: a concurrent atomic save is published via
            # os.replace, so an unlocked read always sees a complete file.
            tokens = self.list()
            result, reason, method, _ = self._evaluate(request, tokens, classification)
            return result, reason, method

        # Consuming path: the entire read -> check -> increment -> write must be
        # atomic, so it runs under the exclusive lock and re-reads from disk.
        try:
            with file_lock(self._lock_path, self.lock_timeout):
                try:
                    tokens = self.list()
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    # Corrupt/unreadable store: fail closed, never fail open.
                    return (
                        False,
                        f"delegation store unreadable, denying: {exc}",
                        "DELEGATION",
                    )
                result, reason, method, matched_id = self._evaluate(
                    request, tokens, classification
                )
                if result is True and matched_id is not None:
                    updated = [
                        replace(token, uses=token.uses + 1)
                        if token.token_id == matched_id
                        else token
                        for token in tokens
                    ]
                    self.save(updated)
                return result, reason, method
        except LockTimeout as exc:
            # Could not serialize the consume; deny rather than risk a race.
            return False, f"delegation lock unavailable, denying: {exc}", "DELEGATION"

    def _evaluate(
        self,
        request: ActionRequest,
        tokens: list[DelegationToken],
        classification: Classification,
    ) -> tuple[bool | None, str, str, str | None]:
        """Pure evaluation over a token snapshot. Returns the decision tuple
        plus the id of the matched token (or None) so the caller can consume it
        atomically under the lock.

        A token only affects the decision if it is *relevant* to the request:
        same actor, in-scope path, and the requested action appears in the
        token's allowed or denied list. Tokens that do not apply (wrong actor,
        action, or path) are ignored, so unrelated or expired stale tokens never
        turn an approval-required action into a hard DENY (issue #77). DENY is
        reserved for an explicit denial and for a *relevant* grant that is no
        longer usable (revoked/expired/exhausted). Everything else falls through
        to the normal approval path — approval still gates it, nothing is granted
        implicitly.
        """
        if not tokens:
            return None, "no delegation applies", "none", None

        now = datetime.now(timezone.utc)
        evaluated = []
        for token in tokens:
            actor_ok = token.actor == request.actor
            path_ok = _path_matches(request.target, token.allowed_paths)
            action_allowed = request.action in token.allowed_actions
            action_denied = request.action in token.denied_actions
            # Relevant = this token concerns this actor, this path scope, and
            # this action (whether to allow or to deny it).
            relevant = actor_ok and path_ok and (action_allowed or action_denied)

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
            if action_denied:
                mismatches.append(f"denied action: '{request.action}'")

            # 5. actor mismatch
            if not actor_ok:
                mismatches.append(
                    f"actor mismatch: expected actor '{token.actor}', actual actor '{request.actor}'"
                )

            # 6. action mismatch
            if not action_allowed and not action_denied:
                mismatches.append(
                    f"action mismatch: expected action in {token.allowed_actions}, actual action '{request.action}'"
                )

            # 7. path mismatch
            if not path_ok:
                mismatches.append(
                    f"path mismatch: expected path scope in {token.allowed_paths}, actual target '{request.target}'"
                )

            # 8. critical flag missing
            if classification == Classification.CRITICAL and not token.critical:
                mismatches.append("critical flag missing")

            evaluated.append((token, mismatches, relevant, action_denied))

        # 1. Full match → ALLOW.
        for token, mismatches, _relevant, _denied in evaluated:
            if not mismatches:
                return (
                    True,
                    f"delegated by {token.token_id}: {token.reason}",
                    "DELEGATION",
                    token.token_id,
                )

        # 2. Explicit denial by a relevant token → DENY (never weakened).
        for token, mismatches, relevant, action_denied in evaluated:
            if relevant and action_denied:
                return (
                    False,
                    f"delegation token {token.token_id} explicitly denies action '{request.action}'",
                    "DELEGATION",
                    None,
                )

        # 3. A relevant grant blocked only by a missing critical flag → defer to
        #    approval (unchanged behavior).
        for token, mismatches, relevant, _denied in evaluated:
            if relevant and mismatches == ["critical flag missing"]:
                reason = f"delegation token {token.token_id} mismatched: critical flag missing"
                return None, reason, "DELEGATION", None

        # 4. A relevant grant exists but is no longer usable (revoked/expired/
        #    exhausted) → DENY with diagnostics. Only relevant tokens count, so a
        #    stale unrelated token cannot block the request here.
        relevant_blocking = [
            (token, mismatches)
            for token, mismatches, relevant, _denied in evaluated
            if relevant
        ]
        if relevant_blocking:
            diagnostics = [
                f"delegation token {token.token_id} mismatched: {', '.join(mismatches)}"
                for token, mismatches in relevant_blocking
            ]
            return False, "; ".join(diagnostics), "DELEGATION", None

        # 5. No token applies to this request → no delegation matched. Fall
        #    through to the normal approval path rather than denying because of
        #    unrelated or expired tokens (issue #77).
        return None, "no delegation matched", "none", None


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


def delegation_status(token: DelegationToken, now: datetime | None = None) -> str:
    """Derived, human-readable status for display/diagnostics only.

    Returns ``"active"`` or a comma-joined combination of ``revoked`` /
    ``expired`` / ``exhausted``. This is observability output; it does NOT affect
    authorization (``_evaluate`` remains the single source of truth).
    """
    now = now or datetime.now(timezone.utc)
    flags = []
    if token.revoked:
        flags.append("revoked")
    if _parse_datetime(token.expires_at) <= now:
        flags.append("expired")
    if token.uses >= token.max_uses:
        flags.append("exhausted")
    return ", ".join(flags) if flags else "active"


def is_broad_delegation(token: DelegationToken) -> bool:
    """True when the token's path scope is unbounded — a wildcard ``"*"`` or an
    empty path list. Observability flag only; does NOT affect authorization."""
    paths = token.allowed_paths
    return (not paths) or ("*" in paths)


def _parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except PermissionError:
        pass
