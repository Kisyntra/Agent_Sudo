from __future__ import annotations

import importlib.resources
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agent_sudo.approvals import CONFIG_PATH
from agent_sudo.delegations import DELEGATIONS_PATH


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(*, repo_root: Path | None = None) -> list[DoctorCheck]:
    root = repo_root or Path.cwd()
    checks = [
        _python_version_check(),
        _default_policy_check(),
        _approval_config_check(),
        _writable_file_check(
            "audit log writable", root / ".agent-sudo" / "doctor-audit.jsonl"
        ),
        _writable_file_check("delegation store writable", DELEGATIONS_PATH),
        _personal_data_check(root),
    ]
    return checks


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
    failed_scan = [
        check
        for check in checks
        if check.name == "no personal data in repo" and not check.ok
    ]
    return 1 if failed_required or failed_scan else 0


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
        if check.name == "no personal data in repo":
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


def _personal_data_check(root: Path) -> DoctorCheck:
    script = root / "scripts" / "check_no_personal_data.py"
    if not script.exists():
        return DoctorCheck(
            "no personal data in repo", False, f"missing scanner: {script}"
        )
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    detail = completed.stdout.strip() or completed.stderr.strip()
    return DoctorCheck("no personal data in repo", completed.returncode == 0, detail)


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
