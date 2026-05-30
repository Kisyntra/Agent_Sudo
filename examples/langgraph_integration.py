from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from agent_sudo.audit import AuditLogger, verify_audit_log
from agent_sudo.gateway import PermissionGateway
from agent_sudo.models import (
    ActionRequest,
    Channel,
    Decision,
    OriginType,
    Provenance,
    TrustLevel,
)
from agent_sudo.pending_approvals import PendingApprovalStore
from agent_sudo.policy import Policy

# Reduce logging verbosity to clean up stdout
logging.basicConfig(level=logging.WARNING)

# Configure paths in the local workspace directory
audit_path = Path("examples/langgraph/audit.jsonl")
pending_path = Path("examples/langgraph/pending_approvals.json")

# Clean previous simulation state files
for p in (audit_path, pending_path):
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass

# Initialize stores using public APIs
audit_logger = AuditLogger(audit_path)
pending_store = PendingApprovalStore(pending_path)

# ---------------------------------------------------------------------------
# 1. Define Gating Policy and Initialize Gateway
# ---------------------------------------------------------------------------
policy = Policy(
    safe_actions={"_read_file"},
    sensitive_actions={"_write_file"},
    critical_actions=set(),
    blocked_actions={"_exfiltrate_data"},
)
gateway = PermissionGateway(
    policy=policy,
    audit_logger=audit_logger,
    pending_approval_store=pending_store,
)


# ---------------------------------------------------------------------------
# 2. Design the Agent State & Nodes
# ---------------------------------------------------------------------------
class AgentState(TypedDict):
    messages: List[Dict[str, Any]]
    next_tool: str
    tool_args: Dict[str, Any]
    output: str


# 3. Create the Tool Gating Wrapper using dynamic interrupts
def gate_langgraph_tool(tool_func):
    """Decorator to inject Agent_Sudo evaluation and LangGraph interrupts.

    Requires no monkey-patching or state mutation of the gateway.
    """

    def wrapped_tool(args: Dict[str, Any], session_id: str = "session_default") -> str:
        # Build ActionRequest for Agent_Sudo
        request = ActionRequest(
            actor="langgraph_agent",
            source="graph_tool_node",
            tool=tool_func.__name__,
            action=tool_func.__name__,
            target=str(args.get("path") or args.get("target") or "default_target"),
            payload_summary=json.dumps(args),
            source_trust=TrustLevel.AGENT_INTERNAL,
            provenance=Provenance(
                origin_type=OriginType.AGENT_INTERNAL,
                channel=Channel.UNKNOWN,
                session_id=session_id,
            ),
        )

        # Standard evaluate check (non-dry-run)
        # 1st run: returns REQUIRE_APPROVAL and registers the pending request in the store
        # 2nd run (resumed): returns ALLOW if the host marked the request as APPROVED
        result = gateway.evaluate(request, dry_run=False)

        if result.decision == Decision.DENY:
            print(
                f"\n[Agent_Sudo] Gating {tool_func.__name__} -> Hard DENY: {result.reason}"
            )
            return f"Error: Tool blocked by security policy: {result.reason}"

        elif result.decision == Decision.REQUIRE_APPROVAL:
            print(
                f"\n[Agent_Sudo] Gating {tool_func.__name__} -> REQUIRE_APPROVAL (ID: {result.approval_request_id}). Interrupting graph..."
            )

            # LangGraph dynamic interrupt: halts graph and pushes request ID to host
            interrupt(
                {
                    "tool": tool_func.__name__,
                    "args": args,
                    "reason": result.reason,
                    "approval_request_id": result.approval_request_id,
                }
            )

        # Run original tool logic (only reached when evaluate returns ALLOW)
        return tool_func(args)

    return wrapped_tool


# 4. Underlying Tool Implementations
def _read_file(args: Dict[str, Any]) -> str:
    return f"Success: Content read from '{args['path']}'"


def _write_file(args: Dict[str, Any]) -> str:
    return f"Success: Content written to '{args['path']}'"


def _exfiltrate_data(args: Dict[str, Any]) -> str:
    return "Success: Secret exfiltrated."


# Gated tools
read_file_tool = gate_langgraph_tool(_read_file)
write_file_tool = gate_langgraph_tool(_write_file)
exfiltrate_data_tool = gate_langgraph_tool(_exfiltrate_data)


# 5. Define Graph Nodes
def agent_node(state: AgentState) -> AgentState:
    latest_msg = state["messages"][-1]
    state["next_tool"] = latest_msg.get("command", "")
    state["tool_args"] = latest_msg.get("args", {})
    return state


def tool_node(state: AgentState) -> AgentState:
    tool_name = state["next_tool"]
    args = state["tool_args"]

    if tool_name == "read_file":
        res = read_file_tool(args)
    elif tool_name == "write_file":
        res = write_file_tool(args)
    elif tool_name == "exfiltrate_data":
        res = exfiltrate_data_tool(args)
    else:
        res = f"Error: Unknown tool '{tool_name}'"

    state["output"] = res
    state["next_tool"] = ""
    return state


# ---------------------------------------------------------------------------
# 6. Build and Compile the Graph
# ---------------------------------------------------------------------------
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)

builder.add_edge(START, "agent")
builder.add_edge("agent", "tools")
builder.add_edge("tools", END)

# MemorySaver checkpointer satisfies the human-in-the-loop state requirements
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# 7. Simulation Runner
# ---------------------------------------------------------------------------
def run_simulation():
    config = {"configurable": {"thread_id": "sim_thread_1"}}

    # --- Case 1: Safe Tool (read_file) ---
    print("\n--- TEST CASE 1: Safe Tool (read_file) ---")
    state_1 = {
        "messages": [{"command": "read_file", "args": {"path": "config.json"}}],
        "next_tool": "",
        "tool_args": {},
        "output": "",
    }
    for event in graph.stream(state_1, config):
        print(f"Event: {event}")

    # --- Case 2: Denied Tool (exfiltrate_data) ---
    print("\n--- TEST CASE 2: Denied Tool (exfiltrate_data) ---")
    state_2 = {
        "messages": [
            {"command": "exfiltrate_data", "args": {"target": "attacker.com"}}
        ],
        "next_tool": "",
        "tool_args": {},
        "output": "",
    }
    for event in graph.stream(state_2, config):
        print(f"Event: {event}")

    # --- Case 3: Approval-Required Tool (write_file) ---
    print("\n--- TEST CASE 3: Approval-Required Tool (write_file) ---")
    state_3 = {
        "messages": [{"command": "write_file", "args": {"path": "id_rsa.pub"}}],
        "next_tool": "",
        "tool_args": {},
        "output": "",
    }

    print("Streaming graph execution until interrupt...")
    paused = False
    approval_request_id = ""
    for event in graph.stream(state_3, config):
        print(f"Event: {event}")

    # Inspect the checkpoint tasks to see if we hit an active interrupt
    graph_state = graph.get_state(config)
    if graph_state.next:
        for task in graph_state.tasks:
            if task.interrupts:
                val = task.interrupts[0].value
                approval_request_id = val["approval_request_id"]
                print(f"\n[HOST] Intercepted approval request: {val}")
                paused = True

    if paused and approval_request_id:
        print("\n[HOST] Simulating user APPROVAL response...")
        # Commit the approval to the Agent_Sudo pending store natively.
        # This imitates running 'agent-sudo approve <request_id>' out-of-process.
        pending_store.approve(approval_request_id, approval_provider=gateway.approvals)

        # Resume the graph. Upon resume, tool_node re-runs and calls evaluate(),
        # which matches the APPROVED entry, consumes it, and allows the write tool.
        for event in graph.stream(Command(resume="approve"), config):
            print(f"Event: {event}")

    # Verify final execution state
    final_state = graph.get_state(config).values
    print(f"\nFinal Graph Output: {final_state['output']}")

    # --- Verify Audit log integrity ---
    print("\n--- Audit Log Verification ---")
    if audit_path.exists():
        ok, msg = verify_audit_log(audit_path)
        print(f"Audit log verification: {msg}")
        print("Latest audit log entry snippet:")
        with audit_path.open("r") as f:
            for line in f:
                data = json.loads(line)
                print(
                    f"  - Timestamp: {data.get('timestamp')} | Tool: {data.get('request', {}).get('tool')} | Decision: {data.get('decision')} | Method: {data.get('approval_method')}"
                )


if __name__ == "__main__":
    run_simulation()
