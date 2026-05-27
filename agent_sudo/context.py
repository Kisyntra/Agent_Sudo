from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeContext:
    cwd: str
    configured_workspace: str | None
    effective_workspace: str
    repo_root: str | None
    git_branch: str | None
    workspace_detected: bool
    running_from_root: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "cwd": self.cwd,
            "configured_workspace": self.configured_workspace,
            "effective_workspace": self.effective_workspace,
            "repo_root": self.repo_root,
            "git_branch": self.git_branch,
            "workspace_detected": self.workspace_detected,
            "running_from_root": self.running_from_root,
            "warnings": self.warnings,
        }


def _load_config_workspace() -> str | None:
    try:
        config_path = Path.home() / ".agent-sudo" / "config.json"
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                val = data.get("workspace")
                if val is not None:
                    return str(val)
    except Exception:
        pass
    return None


def detect_runtime_context(
    cwd: Path | str | None = None,
    workspace: Path | str | None = None,
) -> RuntimeContext:
    resolved_cwd = None
    warnings: list[str] = []

    if cwd is not None:
        try:
            path_cwd = Path(cwd)
            resolved_cwd = path_cwd.resolve()
            if not resolved_cwd.exists():
                warnings.append(f"cwd path does not exist: {cwd}")
            elif resolved_cwd.is_file():
                resolved_cwd = resolved_cwd.parent
        except Exception as exc:
            warnings.append(f"Failed to resolve cwd {cwd}: {exc}")
            resolved_cwd = None

    if resolved_cwd is None:
        try:
            resolved_cwd = Path.cwd().resolve()
        except OSError as exc:
            warnings.append(f"Failed to get current working directory: {exc}")
            resolved_cwd = Path("/").resolve()

    configured_workspace_str = None
    if workspace is not None:
        configured_workspace_str = str(workspace)
    else:
        configured_workspace_str = os.environ.get("AGENT_SUDO_WORKSPACE")
        if configured_workspace_str is None:
            configured_workspace_str = _load_config_workspace()

    effective_workspace = None
    workspace_detected = False

    if configured_workspace_str is not None:
        try:
            path_workspace = Path(configured_workspace_str)
            resolved_workspace = path_workspace.resolve()
            if resolved_workspace.exists() and resolved_workspace.is_dir():
                effective_workspace = resolved_workspace
                workspace_detected = True
            else:
                warnings.append(f"Configured workspace path is invalid or inaccessible: {configured_workspace_str}")
                effective_workspace = resolved_cwd
                workspace_detected = False
        except Exception as exc:
            warnings.append(f"Failed to resolve configured workspace {configured_workspace_str}: {exc}")
            effective_workspace = resolved_cwd
            workspace_detected = False
    else:
        effective_workspace = resolved_cwd
        workspace_detected = False

    repo_root = None
    git_branch = None

    if effective_workspace.exists() and effective_workspace.is_dir() and shutil.which("git") is not None:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=effective_workspace,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                repo_root = str(Path(completed.stdout.strip()).resolve())
                if configured_workspace_str is None:
                    workspace_detected = True
                
                branch_completed = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=effective_workspace,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if branch_completed.returncode == 0:
                    git_branch = branch_completed.stdout.strip()
                    if git_branch == "HEAD":
                        sha_completed = subprocess.run(
                            ["git", "rev-parse", "--short", "HEAD"],
                            cwd=effective_workspace,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        if sha_completed.returncode == 0:
                            git_branch = f"HEAD (detached at {sha_completed.stdout.strip()})"
        except Exception as exc:
            warnings.append(f"Git command failed: {exc}")
    elif shutil.which("git") is None:
        warnings.append("git executable not found")

    running_from_root = effective_workspace == Path("/").resolve()

    if running_from_root:
        sys.stderr.write("Warning: running from root directory.\n")
    if not workspace_detected:
        sys.stderr.write("Warning: no workspace detected.\n")

    return RuntimeContext(
        cwd=str(resolved_cwd),
        configured_workspace=configured_workspace_str,
        effective_workspace=str(effective_workspace),
        repo_root=repo_root,
        git_branch=git_branch,
        workspace_detected=workspace_detected,
        running_from_root=running_from_root,
        warnings=warnings,
    )
