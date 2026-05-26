from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from agent_sudo import __version_label__


def get_git_root() -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return Path(completed.stdout.strip())
    except OSError:
        pass
    return None


def is_working_tree_dirty(git_root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=git_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(completed.stdout.strip())


def version_key(tag: str) -> tuple[int, ...]:
    matches = re.findall(r"\d+", tag)
    return tuple(int(x) for x in matches)


def get_latest_git_tag(git_root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "tag"],
        cwd=git_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    tags = [t.strip() for t in completed.stdout.splitlines() if t.strip()]
    if not tags:
        return None
    tags.sort(key=version_key)
    return tags[-1]


def handle_upgrade(*, check_only: bool = False, allow_dirty: bool = False) -> int:
    git_root = get_git_root()
    if not git_root:
        print("This installation is not inside a git repository.", file=sys.stderr)
        print("\nTo upgrade agent-sudo manually, please run:\n  pip install --upgrade agent-sudo", file=sys.stderr)
        return 1

    # Show warning about local state preservation
    print("NOTE: Local state, audit logs, and delegations under ~/.agent-sudo will be preserved.")

    # Get current branch and commit
    branch_cmd = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root, capture_output=True, text=True)
    commit_cmd = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=git_root, capture_output=True, text=True)
    current_branch = branch_cmd.stdout.strip() if branch_cmd.returncode == 0 else "unknown"
    current_commit = commit_cmd.stdout.strip() if commit_cmd.returncode == 0 else "unknown"

    print(f"Current installed version: {__version_label__}")
    print(f"Current Git branch: {current_branch}")
    print(f"Current Git commit: {current_commit}")

    # Fetch latest tags
    print("Fetching tags from origin...")
    fetch_cmd = subprocess.run(["git", "fetch", "--tags"], cwd=git_root, capture_output=True, text=True)
    if fetch_cmd.returncode != 0:
        print("Warning: Failed to fetch tags from origin.", file=sys.stderr)

    latest_tag = get_latest_git_tag(git_root)
    if latest_tag:
        print(f"Latest available tag: {latest_tag}")
        is_newer = version_key(latest_tag) > version_key(__version_label__)
        print(f"Upgrade available: {'Yes' if is_newer else 'No'}")
    else:
        print("Latest available tag: unknown")
        is_newer = False

    if check_only:
        return 0

    # Verify working tree is clean unless allow_dirty is True
    if is_working_tree_dirty(git_root) and not allow_dirty:
        print("Error: Git working tree has uncommitted changes.", file=sys.stderr)
        print("Please commit or stash your changes, or pass --allow-dirty to ignore.", file=sys.stderr)
        return 1

    # Pull current branch
    print(f"Pulling latest changes on branch {current_branch}...")
    pull_cmd = subprocess.run(["git", "pull"], cwd=git_root)
    if pull_cmd.returncode != 0:
        print("Error: git pull failed.", file=sys.stderr)
        return 1

    # Reinstall
    print("Reinstalling agent-sudo in editable mode...")
    reinstall_cmd = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], cwd=git_root)
    if reinstall_cmd.returncode != 0:
        print("Error: pip installation failed.", file=sys.stderr)
        return 1

    # Verify installation
    print("Verifying installation...")
    try:
        subprocess.run(["agent-sudo", "--version"], check=True)
        subprocess.run(["agent-sudo-mcp", "--version"], check=True)
        subprocess.run(["agent-sudo", "doctor"], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"Warning: Verification failed ({exc}).", file=sys.stderr)
        # Fallback to sys.executable verification
        try:
            subprocess.run([sys.executable, "-m", "agent_sudo.gateway", "--version"], check=True)
            subprocess.run([sys.executable, "-m", "agent_sudo.gateway", "doctor"], check=True)
        except subprocess.CalledProcessError:
            print("Error: Post-upgrade verification failed.", file=sys.stderr)
            return 1

    print("\nUpgrade completed successfully!")
    print("\nReminder:\n  Restart Claude Desktop / Cursor / Hermes / OpenClaw after upgrading MCP server.")
    return 0
