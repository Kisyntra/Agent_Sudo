# Interoperability Compliance Checklist

This document provides a technical compliance checklist for external agent frameworks and desktop runtimes (like `LexFlow`) to align with the `Agent_Sudo` governance model.

---

## 1. Request and Decision Payload Requirements

Any external client or integration must construct and consume standard payloads:

### ActionRequest Payloads
The payload representing a tool request **must** contain:
- [ ] **`actor`**: Unique string identifying the requesting system.
- [ ] **`source`**: String identifying the instruction source.
- [ ] **`tool`**: Namespace of the targeted tool.
- [ ] **`action`**: Verb of the tool action.
- [ ] **`target`**: Target resource parameters (e.g. file path).
- [ ] **`payload_summary`**: Description of what the tool call does.
- [ ] **`source_trust`**: One of: `"USER_DIRECT"`, `"AGENT_INTERNAL"`, `"EXTERNAL_CONTENT"`, `"UNKNOWN"`.

### PolicyDecision Payloads
The engine evaluation output **must** contain:
- [ ] **`decision`**: One of: `"ALLOW"`, `"DENY"`, `"REQUIRE_APPROVAL"`, `"REQUIRE_STRONG_APPROVAL"`.
- [ ] **`classification`**: One of: `"SAFE"`, `"SENSITIVE"`, `"CRITICAL"`, `"BLOCKED"`.
- [ ] **`reason`**: Descriptive explanation string.
- [ ] **`approval_method`**: One of: `"none"`, `"cli_confirm"`, `"passphrase"`, `"delegation"`.

---

## 2. Cryptographic Hash-Chaining Mechanics

To log events compatibly, your local logger **must** enforce these hash-chaining rules:

- [ ] **Genesis Hash**: The first record in an audit log file must have a `previous_hash` of 64 zeros: `"0000000000000000000000000000000000000000000000000000000000000000"`.
- [ ] **Key Exclusions**: Remove `entry_hash` key from the dictionary before computing the hash.
- [ ] **Canonical Sorting**: Sort all JSON keys alphabetically.
- [ ] **Compact Output**: Format JSON with no extra spaces after separators (e.g. `{"a":1,"b":2}`).
- [ ] **Concatenation**: Concatenate the `previous_hash` string value directly with the canonical JSON string.
- [ ] **Hash Algorithm**: Hash the concatenated bytes with SHA-256 and output it as a lowercase hex string.

---

## 3. Approval Semantics

If your integration implements interactive human approvals, it **must** enforce these rules:

- [ ] **Single-Use Consumption**: Once an approval is approved and used to allow an action, it must be marked `"USED"` immediately and cannot be reused for subsequent tool calls.
- [ ] **TTL Enforcement**: Pending approvals must expire and transition to `"EXPIRED"` status if not confirmed within the designated time window (default 120 seconds).
- [ ] **No Auto-Approve**: Non-interactive runs (without TTY or explicit operator session) must never auto-approve sensitive/critical actions.

---

## 4. Delegation Semantics

If checking delegations in-process against `~/.agent-sudo/delegations.json`, your engine **must** enforce:

- [ ] **Exact Actor Matching**: The requesting `actor` name must exactly match the delegation token's `actor` property.
- [ ] **Action Scope Check**: The requested `action` must exist in the token's `allowed_actions` list and must **not** exist in its `denied_actions` list.
- [ ] **Path Bound Resolution**: The `target` path must reside within the folder boundaries defined in `allowed_paths`. All paths must be fully resolved (`Path.resolve()`) to prevent directory traversal escapes.
- [ ] **Usage Decrementing**: Every time a delegated tool call is executed, the `uses` count in the token must increment. Once `uses` reaches `max_uses`, the token is invalid.
- [ ] **Thread Safety**: Reading and writing the delegation store file must be secured using file locks or thread synchronization to prevent race conditions.

---

## 5. Audit Verification Expectations

To confirm that your integration's logs are compliant, they must pass the reference checker:

- [ ] Run `agent-sudo verify-audit <path_to_log>` against your log file.
- [ ] Verify the utility exits with `0` and outputs `audit log verified`.

---

## 6. Python Integration Helpers

For Python-based clients or integrations, `Agent_Sudo` distributes a lightweight, standard library-only helper module: [spec_helpers.py](../../agent_sudo/spec_helpers.py).

Developers can import it directly to serialize and verify hash chains in-process:
```python
from agent_sudo.spec_helpers import (
    canonicalize_record,
    compute_entry_hash,
    verify_hash_chain,
    verify_jsonl_file,
)
```
This enables zero-dependency audit logging and verification in single-process desktop applications.
