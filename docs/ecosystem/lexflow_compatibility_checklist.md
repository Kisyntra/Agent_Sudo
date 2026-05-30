# LexFlow Interoperability Compatibility Checklist

Use this checklist to verify that the LexFlow TypeScript audit log emitter matches the `Agent_Sudo` universal schema and hash chain specifications.

---

## 1. Schema Fields & Taxonomy Checklist

*   [ ] **`event_type`**: The record uses `tool_execution` for all MCP/tool execution log entries.
*   [ ] **`schema_version`**: The top-level key `schema_version` is present and set to `agent-sudo/0.4.0` (or matching tag).
*   [ ] **`approval_command`**: Field is omitted or set to `null` if the execution occurs in-process without CLI approval paths.
*   [ ] **`approval_expires_at`**: Set as a standard ISO 8601 absolute timestamp. Relative `expires_in_seconds` is excluded or marked optional.
*   [ ] **`payload_summary`**: Normalized to a clean, truncated text string summarizing arguments (e.g., max 128 characters).
*   [ ] **Extension Fields**: Custom metadata fields are prefixed with `lexflow_` (e.g. `lexflow_session_id`, `lexflow_thread_id`) to avoid collision.

---

## 2. Cryptographic Hash-Chain Checklist

*   [ ] **Previous Hash Initialization**: The very first line of the log uses a `previous_hash` of exactly `64` zeros (`"0" * 64`).
*   [ ] **Chain Linkage**: Every subsequent line's `previous_hash` matches the computed `entry_hash` of the immediately preceding line.
*   [ ] **Excluded Key**: The key `entry_hash` is stripped from the dictionary *before* canonical serialization.
*   [ ] **Recursive Key Sorting**: Keys at all levels of object nesting are sorted alphabetically.
*   [ ] **Compact JSON Formatting**: The serialization is compact, using no whitespace spaces around separators (e.g., standard Python `separators=(',', ':')` equivalence).
*   [ ] **UTF-8 Encoded**: The final string is encoded as UTF-8 bytes before hashing.
*   [ ] **SHA-256 Hashing**: The `entry_hash` is computed as:
    `SHA-256( previous_hash_hex_string + UTF-8_canonical_JSON_bytes )`

---

## 3. CI & Verification Checklist

*   [ ] **Subprocess Test Execution**: LexFlow's test suite generates `~/.lexflow/mcp.log` during simulated runs.
*   [ ] **Verify Command Check**: Run `agent-sudo verify-audit ~/.lexflow/mcp.log`.
*   [ ] **Return Code Validation**: Test suite asserts that the verify process exits with code `0`.
*   [ ] **Handling blank lines**: The emitter does not write trailing empty objects (blank lines are skipped by the verifier).
*   [ ] **UTF-8 Byte Parity**: Verify that non-ASCII unicode strings match the verifier's encoding rules.
