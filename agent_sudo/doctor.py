from __future__ import annotations

import importlib.resources
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent_sudo.approvals import CONFIG_PATH
from agent_sudo.delegations import (
    DelegationStore,
    default_delegations_path,
    is_broad_delegation,
)


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(*, repo_root: Path | None = None) -> list[DoctorCheck]:
    # doctor reports user readiness only. Repository/contributor hygiene
    # (e.g. the personal-data scanner) is a CI concern run via
    # scripts/check_no_personal_data.py, not surfaced to evaluators here.
    #
    # All probes target the single home state root (~/.agent-sudo, where the
    # approval config and delegation store live) so doctor reports one
    # consistent location and never litters a .agent-sudo/ directory into the
    # current working directory. ``repo_root`` is accepted for backward
    # compatibility but no longer changes where state is probed.
    del repo_root
    state_root = default_delegations_path().parent
    return [
        _python_version_check(),
        _default_policy_check(),
        _approval_config_check(),
        _writable_file_check("audit log writable", state_root / "doctor-audit.jsonl"),
        _writable_file_check("delegation store writable", default_delegations_path()),
        _broad_delegations_check(),
    ]


def doctor_exit_code(checks: list[DoctorCheck]) -> int:
    required = {
        "Python version OK",
        "default policy exists",
        "audit log writable",
        "delegation store writable",
    }
    failed_required = [
        check for check in checks if check.name in required and not check.ok
    ]
    return 1 if failed_required else 0


def format_doctor_checks(checks: list[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        status = "OK" if check.ok else "WARN"
        if check.name in {
            "Python version OK",
            "default policy exists",
            "audit log writable",
            "delegation store writable",
        }:
            status = "OK" if check.ok else "FAIL"
        if check.name == "approval config exists" and not check.ok:
            lines.append(
                f"{status}: {check.name} - {check.detail}\n\n"
                "APPROVALS: NOT INITIALIZED\n\n"
                "Recommended:\n"
                "agent-sudo init-approval"
            )
        else:
            lines.append(f"{status}: {check.name} - {check.detail}")
    return "\n".join(lines)


def _python_version_check() -> DoctorCheck:
    ok = sys.version_info >= (3, 10)
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return DoctorCheck("Python version OK", ok, f"running Python {version}")


def _default_policy_check() -> DoctorCheck:
    policy = importlib.resources.files("agent_sudo.config").joinpath(
        "default_policy.yaml"
    )
    exists = Path(str(policy)).exists()
    return DoctorCheck(
        "default policy exists", exists, "agent_sudo/config/default_policy.yaml"
    )


def _approval_config_check() -> DoctorCheck:
    exists = CONFIG_PATH.exists()
    detail = (
        _display_path(CONFIG_PATH)
        if exists
        else "not initialized: run agent-sudo init-approval"
    )
    return DoctorCheck("approval config exists", exists, detail)


def _broad_delegations_check() -> DoctorCheck:
    # Observability warning only (not in the required set, so it never fails the
    # exit code). A broad (path="*") token allows or blocks ALL matching actions
    # while active, and — once stale — can blanket-deny them; surface it so it is
    # not silently masking or breaking approvals.
    path = default_delegations_path()
    try:
        tokens = DelegationStore(path).list() if path.exists() else []
    except (OSError, ValueError) as exc:
        return DoctorCheck(
            "delegation scope", False, f"could not read delegation store: {exc}"
        )
    broad = [token for token in tokens if is_broad_delegation(token)]
    if not broad:
        return DoctorCheck(
            "delegation scope", True, "no broad (path=*) delegations present"
        )
    ids = ", ".join(token.token_id for token in broad)
    return DoctorCheck(
        "delegation scope",
        False,
        f"{len(broad)} broad (path=*) delegation(s) present: {ids}; "
        "these allow or block all matching actions — review with "
        "`agent-sudo delegate list`",
    )


def _writable_file_check(name: str, path: Path) -> DoctorCheck:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=path.name, dir=path.parent, delete=True
        ):
            pass
        return DoctorCheck(name, True, _display_path(path))
    except OSError as exc:
        return DoctorCheck(name, False, str(exc))


def _display_path(path: Path) -> str:
    resolved = path.expanduser()
    home = Path.home()
    try:
        return f"~/{resolved.relative_to(home)}"
    except ValueError:
        pass
    try:
        return str(resolved.relative_to(Path.cwd()))
    except ValueError:
        return str(resolved)
