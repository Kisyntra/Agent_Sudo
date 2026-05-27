from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RuntimeContext:
    cwd: str
    repo_root: str | None
    git_branch: str | None
    workspace_detected: bool
    running_from_root: bool
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "cwd": self.cwd,
            "repo_root": self.repo_root,
            "git_branch": self.git_branch,
            "workspace_detected": self.workspace_detected,
            "running_from_root": self.running_from_root,
            "warnings": self.warnings,
        }


def detect_runtime_context(cwd: Path | str | None = None) -> RuntimeContext:
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

    running_from_root = resolved_cwd == Path("/").resolve()
    repo_root = None
    git_branch = None

    # Check if git is installed and directory exists/is a directory
    if resolved_cwd.exists() and resolved_cwd.is_dir() and shutil.which("git") is not None:
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=resolved_cwd,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                repo_root = str(Path(completed.stdout.strip()).resolve())
                
                # Fetch branch name
                branch_completed = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=resolved_cwd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if branch_completed.returncode == 0:
                    git_branch = branch_completed.stdout.strip()
                    if git_branch == "HEAD":
                        # Detached HEAD, resolve short commit hash
                        sha_completed = subprocess.run(
                            ["git", "rev-parse", "--short", "HEAD"],
                            cwd=resolved_cwd,
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

    workspace_detected = repo_root is not None

    if running_from_root:
        sys.stderr.write("Warning: running from root directory.\n")
    if not workspace_detected:
        sys.stderr.write("Warning: no workspace detected.\n")

    return RuntimeContext(
        cwd=str(resolved_cwd),
        repo_root=repo_root,
        git_branch=git_branch,
        workspace_detected=workspace_detected,
        running_from_root=running_from_root,
        warnings=warnings,
    )
