# External Validation Readiness Report

This report evaluates `Agent_Sudo`'s readiness for its first independent verifier-compatible implementation (specifically targeting the `LexFlow` audit-log emitter) and maps out the core implementation traps, quick-start guides, and developer debugging path.

---

## 1. Review and Gap Analysis

### A. If LexFlow started implementation today:
1.  **What would fail first?**
    *   **Unicode Escaping**: The emitter's hashes would fail immediately if any non-ASCII characters (e.g. curly quotes, accented characters, currency symbols) are written to fields like `payload_summary` or `reason`. Python's default `json.dumps` escapes these to ASCII representation (e.g. `\u20ac` for `€`), whereas JS `JSON.stringify` does not.
    *   **Timestamp Format**: Standard JavaScript `new Date().toISOString()` produces 3-decimal millisecond precision (e.g. `2026-05-29T15:53:00.000Z`). The Python `AuditLogger` generates variable precision or excludes sub-seconds (e.g. `2026-05-29T15:53:00Z`). Any difference in date string representation will break the hash byte-for-byte.
2.  **What would confuse implementers?**
    *   **Nested Array Key Sorting**: Emitters might assume that "key sorting" only applies to the top-level keys of the audit record. They would be confused when their hashes fail on records containing nested arrays of objects (like `approval_attempts`), where the inner objects' keys must also be sorted alphabetically.
    *   **Omitted Fields**: JS developers often omit keys or set them to `undefined` for optional fields (e.g., `approval_command`). Since `JSON.stringify` completely drops `undefined` values, the output string will lack these keys, causing hash mismatches against Python's default model representations where these fields are written as `""` or `null`.
3.  **What assumptions are only documented in Python code?**
    *   **Blank Line Skipping**: The fact that the verifier ignores empty lines (`line.strip() == ""`) is only visible in `verify_jsonl_file()`.
    *   **ASCII Unicode Escaping**: Python's implicit behavior of escaping non-ASCII unicode by default in `json.dumps`.
    *   **Hash Encoding Concatenation**: The specific byte concatenation: `hash = SHA-256( ASCII_previous_hash_string + UTF-8_canonical_JSON_bytes )`.

---

### B. What a TypeScript engineer needs to know (not currently obvious):
1.  **`undefined` Removal Trap**: If an optional field in TS is type-defined as `field?: string`, assigning `undefined` or omitting it removes the key entirely from the JSON string. Developers must explicitly assign `null` or `""` to match Python model defaults.
2.  **Number vs Float Serialization**: JS uses `Number` for all numeric values. `10.0` and `10` are identical in JS memory and both serialize to `"10"`. Python serializes `10.0` as `"10.0"`. Therefore, TS engineers must strictly avoid decimal floats in audit logs.
3.  **Recursion Depth**: Sorting must apply recursively to objects nested inside arrays (e.g. `approval_attempts: [ { "approver": "user", "status": "APPROVED" } ]`).

---

### C. What verifier errors would be difficult to debug?
*   **`entry_hash mismatch`**: The CLI verifier outputs `line X: entry_hash mismatch` but does not output the *actual* calculated hash, the *expected* hash, or the *canonical string* that was hashed. If a single whitespace or key-sorting error occurs, the developer has no way of telling which field or character is mismatched without manually inspecting the binary differences or modifying the Python source code to print them.
*   **`previous_hash mismatch`**: The verifier returns this if a single line fails to verify, causing the rest of the chain to break. It does not output the mismatching values, leaving the engineer to guess if it was a chain-linkage error or a corruption of the prior entry's hash.

---

## 2. Top 10 Implementation Traps
*(Ordered by probability of occurrence)*

1.  **Standard JS `JSON.stringify` Formatting (High Probability)**
    *   *Trap*: Standard formatting library defaults (such as adding spaces or formatting outputs) break the no-whitespace separator rule (`separators=(',', ':')`).
2.  **Omitted/`undefined` Fields vs `null` Defaults (High Probability)**
    *   *Trap*: Omission of optional fields like `approval_expires_in_seconds` or `parent_request_id` in JS/TS. They must be written as `null` or `""` as defined by Python model outputs.
3.  **Non-ASCII Unicode Escaping Mismatch (High Probability)**
    *   *Trap*: JS serializes non-ASCII characters literally (e.g. `€`), while Python serializes them escaped (e.g. `\u20ac`), breaking byte-for-byte parity.
4.  **Key Sorting inside Array Objects (Medium-High Probability)**
    *   *Trap*: Sorting only the top-level keys and failing to sort keys of objects inside nested lists (such as `approval_attempts` elements).
5.  **Sub-second Date Precision Differences (Medium Probability)**
    *   *Trap*: Emitters writing fractional seconds in ISO 8601 strings (e.g. `.000Z` vs no millisecond component).
6.  **Float Stringification Parity (Medium Probability)**
    *   *Trap*: Using floating-point values in logs, which serialize differently in JS/TS (`10` instead of `10.0`), leading to hash failures.
7.  **Carriage Return line endings on Windows (Low-Medium Probability)**
    *   *Trap*: Logging with `\r\n` (CRLF) on Windows instead of standard `\n` (LF) Unix line endings, breaking the line parser logic.
8.  **Empty List Omission (Low-Medium Probability)**
    *   *Trap*: Setting fields like `delegation_chain` or `approval_attempts` to `null` or omitting them instead of initializing to `[]`.
9.  **Genesis Hash Initialization length (Low Probability)**
    *   *Trap*: Initializing `previous_hash` with fewer than 64 zeros, or using a numeric `0`.
10. **Stripping `entry_hash` during previous-hash chaining (Low Probability)**
    *   *Trap*: Including the previous record's `entry_hash` inside the canonical JSON input byte buffer of the *current* record's hash calculation. The current record's `previous_hash` string is concatenated directly, but the current record's `entry_hash` key is stripped.

---

## 3. One-Page External Implementer Quick Start

### Step 1: Initialize the Chain
The first log line (genesis) must set `previous_hash` to exactly 64 hexadecimal zeros:
`"0000000000000000000000000000000000000000000000000000000000000000"`.

### Step 2: Populate the Audit Record
Fill in all schema-required fields. Use `null` or `""` for optional values, and initialize collections to `[]`:
```typescript
const record = {
  timestamp: "2026-05-29T15:53:00Z", // strict ASCII UTC, no milliseconds
  event_type: "gateway_decision",
  schema_version: "agent-sudo/0.4.0",
  request: {
    actor: "agent-name",
    source: "source-name",
    tool: "tool-name",
    action: "action-name",
    target: "target-name",
    payload_summary: "summary",
    risk_hints: [],
    source_trust: "USER_DIRECT",
    provenance: {
      origin_type: "UNKNOWN",
      channel: "unknown",
      authenticated: false,
      authentication_method: "unknown",
      session_id: "",
      request_id: "",
      parent_request_id: "",
      delegation_chain: []
    }
  },
  classification: "SAFE",
  decision: "ALLOW",
  approval_method: "none",
  approval_attempts: [],
  reason: "policy matches",
  dry_run: false,
  approval_request_id: "",
  approval_command: "",
  approval_expires_at: "",
  approval_expires_in_seconds: null,
  previous_hash: "0000000000000000000000000000000000000000000000000000000000000000"
};
```

### Step 3: Canonicalize the Record
1.  Remove the `entry_hash` key if present.
2.  Recursively sort all dictionary/object keys alphabetically.
3.  Serialize to a compact JSON string with no whitespace around separators.
4.  Escape any non-ASCII characters to standard ASCII escapes (e.g. `\u20ac`).

### Step 4: Calculate the Entry Hash
Convert the previous hash hex string and the canonical serialized JSON string to UTF-8 bytes, concatenate them, and calculate the SHA-256 digest:
`entry_hash = hex(SHA-256( previous_hash_string + canonical_serialized_string ))`

### Step 5: Chain and Append
Add the calculated `entry_hash` to the record and write the object as a single-line JSON string terminated with `\n` to your log file:
```bash
# Verify using the agent-sudo CLI
agent-sudo verify-audit ~/.lexflow/mcp.log
```

---

## 4. Documentation Sufficiency Evaluation

### Can an engineer succeed using only the current README, docs/interop, and checklists?

**Almost, but with high risk of initial failure.** 
With the introduction of the Interoperability Test Kit, the technical gap is 90% closed. However, an engineer would still likely hit the following roadblocks:
1.  **Date/Sub-second Precision Trap**: No warning exists in the checklists regarding millisecond formatting mismatch.
2.  **Unicode Escaping Behavior**: The difference between standard JS stringification and Python's ASCII-escaping serialization is undocumented outside of this report.
3.  **Default Value Schema Mapping**: There is no documentation mapping what defaults are expected for optional keys (such as `dry_run: false` or `approval_expires_in_seconds: null`).

### Proposed Documentation Path Improvements:
1.  **Add ISO-8601 Millisecond formatting constraints** directly to the [compatibility checklist](file:///Volumes/Storage/Agent_Sudo/docs/ecosystem/lexflow_compatibility_checklist.md).
2.  **Document Unicode ASCII-escaping rules** in the serialization section of [interoperability_test_kit.md](file:///Volumes/Storage/Agent_Sudo/docs/interop/interoperability_test_kit.md).
3.  **Include an explicit key-defaults table** in the test kit showing how empty fields must be represented to ensure schema alignment.
