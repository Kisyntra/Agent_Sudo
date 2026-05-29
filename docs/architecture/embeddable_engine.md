# Proposal: Embeddable Python Policy Engine

This document explores the design for an optional, in-process Python policy engine mode for `Agent_Sudo`. This allows desktop applications (such as `LexFlow`) to import `Agent_Sudo` as a library and perform validation checks directly in-process without requiring network hops or daemon services.

---

## 1. Proposed API Interface

If integrated as an embeddable library, the engine would expose the following API boundaries:

```python
from pathlib import Path
from agent_sudo.spec import ActionRequest, PolicyDecision
from agent_sudo.engine import InProcessGateway

# 1. Initialize the Gateway in-process
gateway = InProcessGateway(
    policy_path=Path("~/.agent-sudo/policy.yaml"),
    audit_log_path=Path("~/.agent-sudo/mcp-audit.jsonl"),
    delegations_path=Path("~/.agent-sudo/delegations.json"),
    pending_approvals_path=Path("~/.agent-sudo/pending_approvals.json")
)

# 2. Construct an Action Request
request = ActionRequest(
    actor="lexflow-internal",
    source="user",
    tool="filesystem",
    action="write_file",
    target="/path/to/document.lf",
    payload_summary="Save user legal workflow document"
)

# 3. Evaluate the request against policies and delegations
decision: PolicyDecision = gateway.evaluate(request)

if decision.decision == "ALLOW":
    # Execute the local tool directly
    execute_tool()
    gateway.log_success(request, decision)
elif decision.decision in ("REQUIRE_APPROVAL", "REQUIRE_STRONG_APPROVAL"):
    # Create a pending approval state that can be approved via CLI/companion UI
    gateway.create_pending_approval(request, decision)
else:
    # Action blocked by policy
    raise PermissionError(f"Action blocked: {decision.reason}")
```

---

## 2. API Stability Risks of Early Commitment

Committing to a public Python library API too early introduces several major risks:

- **Refactoring Constraints**: Exposing internal classes like `PermissionGateway` or `AuditLogger` as public APIs binds the codebase. Major structural improvements (such as moving from synchronous logic to `async/await` for better GUI integrations, or changing configuration formats) will break client applications.
- **Dependency Versioning**: Library conflicts (e.g., if LexFlow uses a different version of a YAML parser, Pydantic, or cryptographic library than `Agent_Sudo`) can cause runtime symbol crashes.
- **Security Bypass/Mocking**: In-process code can be manipulated. If LexFlow's host process gets compromised, an attacker could monkey-patch or mock the `InProcessGateway.evaluate` method to bypass all checks entirely. A separate daemon process acts as a stronger boundary.
- **Maintenance Overhead**: Supporting backward-compatible Python packaging, version deprecation paths, and different interpreter version compatibility increases the maintenance burden of the project.

---

## 3. Recommendation: Defer Full Engine, Implement Partial Spec Helpers

To align with LexFlow's requirements without taking on early API stability risks, we recommend the following approach:

### Recommendation: **Defer Full Packaging, Publish Audit Spec Helpers**

1. **Defer Full Embedded Engine**: Do not package or document `InProcessGateway` as a stable public library API yet. Keep it internal.
2. **Standardize Schemas and Hashes (Spec-First)**: Publish `POLICY_AUDIT_SCHEMA.md` and define stable JSON schemas.
3. **Provide Lightweight Specs/Audit Module (Partial Implementation)**: 
   Introduce a very small, stable helper module (e.g. `agent_sudo.spec_helpers`) containing only:
   - Schema validation helpers.
   - The cryptographic audit log hash-chaining verification logic.
   This allows LexFlow to validate its own objects and write compatible audit records in-process without invoking the complex approval/policy engine code.

---

## 4. Integration Guidelines for LexFlow (Single-Process App)

LexFlow can align with `Agent_Sudo` immediately using the spec-first approach:

1. **Emitting Audit Logs**:
   LexFlow writes its own tool logs to `~/.agent-sudo/mcp-audit.jsonl` using the standard `AuditRecord` format. LexFlow calculates the hash chain locally by calling the standard SHA-256 canonicalization method.
2. **Checking Delegations**:
   LexFlow reads `~/.agent-sudo/delegations.json` directly to check if a user has stashed active delegations.
3. **Gateway Auditing**:
   The command `agent-sudo verify-audit ~/.agent-sudo/mcp-audit.jsonl` will verify LexFlow's logs seamlessly, ensuring absolute integrity of the unified audit trail.
