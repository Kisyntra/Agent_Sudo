# LexFlow Integration Readiness Report

This report assesses the readiness of `LexFlow` as the first independent external implementation validating `Agent_Sudo` interoperability.

---

## 1. Current Implementation Status
*   **Target Version**: Pinning to `v0.4.0` specification.
*   **Vertical Slice 1**: Emitter-only audit log. Writes JSONL records to `~/.lexflow/mcp.log`.
*   **Verification integration**: The first LexFlow PR will invoke the Python `agent_sudo.spec_helpers.verify_jsonl_file()` via a test subprocess to assert parity.

---

## 2. Expected CI Validation Path
1.  **Log Generation**: LexFlow generates tool execution logs under `~/.lexflow/mcp.log` during test suites.
2.  **Verifier Invocation**: LexFlow's test suite pip-installs `agent-sudo-mcp` (or uses `pipx`) and runs:
    ```bash
    agent-sudo verify-audit ~/.lexflow/mcp.log
    ```
3.  **CI Assertion**: If the verifier exits with code `0`, it validates that the JS/TS emitter output is byte-for-byte compatible with Python's canonical hash-chain spec.

---

## 3. Verifier Integration Path (TypeScript Port)
In Phase 3 of their plan, LexFlow will implement an in-browser TypeScript port of the hash-chain verifier. 
*   **Dependency**: Key sorting recursively in JS before stringifying.
*   **Verification**: The JS port must yield the same SHA-256 hashes as the Python `spec_helpers.py`.

---

## 4. Schema Dependencies & Open Issues

LexFlow's parity depends on resolving the following coordination issues on `Kisyntra/Agent_Sudo`:

| Issue | Title | Impact on LexFlow | Resolution Proposal |
| :--- | :--- | :--- | :--- |
| **#9** | `event_type` taxonomy | Needs reserved type for tool logs | Reserve `tool_execution` for standard executions. |
| **#10** | `payload_summary` shape | Needs standard truncation rule | Keep as free-text, but define standard truncation guidelines. |
| **#11** | `approval_command` UI-neutrality | CLI command string is useless in GUI | Mark `approval_command` as optional (nullable). |
| **#12** | Expiration redundancy | Absolute vs relative mismatch | Use absolute `expires_at` (ISO 8601) as the source of truth. |
| **#13** | `schema_version` placement | Risk of version tampering | Place `schema_version` at top-level of `AuditRecord`. |
| **#14** | Namespace collision | Risk of metadata conflicts | Soft convention recommending runtime prefixes (e.g. `lexflow_`). |

---

## 5. Remaining Risks
1.  **JS key sorting bugs**: If nested objects are not recursively sorted, hashing will fail.
2.  **Date/Float string mismatches**: Floats like `1.0` or ISO timestamps with different millisecond layouts will cause mismatches.
3.  **JSON Stringify separators**: JS `JSON.stringify(obj)` uses whitespace by default if formatted; it must explicitly use compact formatting with no separators spacing.
4.  **CLI error formatting**: `agent-sudo verify-audit` does not print expected vs actual hashes on failure, making CI failures hard to debug.
5.  **UTF-8 encoding drift**: Carriage return differences (`\r\n` vs `\n`) between OS environments during test execution.
