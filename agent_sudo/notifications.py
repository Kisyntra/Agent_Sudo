from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from agent_sudo.models import ApprovalRequest


def send_approval_notification(approval: ApprovalRequest) -> bool:
    """
    Sends a macOS native desktop notification for a pending approval request.
    This function is optional, secure, and non-blocking.
    """
    if sys.platform != "darwin":
        return False

    request = approval.action_request
    action = request.action
    classification = approval.classification.value

    # Secure target summary formulation to avoid leaking secrets
    target_str = request.target.strip() if request.target else ""
    if action == "run_shell_command":
        # Extract command binary/name only, never show full args
        safe_target = target_str.split()[0] if target_str else "command"
    elif action in ("write_file", "read_file", "edit_file", "delete_file"):
        # Extract filename only, never show full path
        try:
            safe_target = Path(target_str).name
        except Exception:
            safe_target = "file"
    else:
        # Fall back to payload summary or truncated target
        safe_target = request.payload_summary or target_str

    if not safe_target:
        safe_target = "action"

    # Truncate target if too long
    if len(safe_target) > 50:
        safe_target = safe_target[:47] + "..."

    title = "Agent_Sudo approval required"
    body = f"{classification} action requested: {action} on {safe_target}\nRun: agent-sudo pending"

    # Truncate body to ensure safety
    if len(body) > 200:
        body = body[:197] + "..."

    # Escape double quotes and backslashes for AppleScript syntax compatibility
    escaped_title = title.replace("\\", "\\\\").replace('"', '\\"')
    escaped_body = body.replace("\\", "\\\\").replace('"', '\\"')

    applescript = f'display notification "{escaped_body}" with title "{escaped_title}"'

    try:
        # Execute osascript using shell=False to prevent shell injection vulnerabilities
        res = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True,
            check=False
        )
        return res.returncode == 0
    except Exception:
        return False
