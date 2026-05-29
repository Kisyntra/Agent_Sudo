# Specification: PolicyDecision and AuditRecord Schemas

This document defines the stable data schemas and cryptographic verification rules for `Agent_Sudo` decisions and audit logs. This specification allows external, single-process desktop applications (like `LexFlow`) to align with `Agent_Sudo` decision formats and write compatible, cryptographically verifiable audit records.

---

## 1. Core Model Representations

`Agent_Sudo` standardizes six key concepts:
1. **actor**: A unique string identifying the agent, client, or identity requesting the tool execution (e.g. `"mcp-client"`, `"lexflow-internal"`).
2. **tool**: The domain namespace of the tool being called (e.g. `"filesystem"`, `"shell"`, `"web_browser"`).
3. **args** / **target**: The parameter or target of the tool action (e.g. `"/path/to/file.txt"` or `"git status"`).
4. **risk** / **classification**: The risk level classification determined by policy: `"SAFE"`, `"SENSITIVE"`, `"CRITICAL"`, or `"BLOCKED"`.
5. **TTL**: The lifetime constraint (in seconds) for a pending approval or token expiration.
6. **max-use**: The limit on how many times a delegation token or approval can be consumed.

---

## 2. PolicyDecision Schema

The `PolicyDecision` object represents the outcome of a gateway evaluation.

### Required Fields:
- **`decision`**: The final action authorization. Must be one of:
  - `"ALLOW"`: Action may proceed.
  - `"DENY"`: Action must be blocked.
  - `"REQUIRE_APPROVAL"`: Requires operator yes/no confirmation.
  - `"REQUIRE_STRONG_APPROVAL"`: Requires operator passphrase verification.
- **`classification`**: The evaluated risk level. Must be one of: `"SAFE"`, `"SENSITIVE"`, `"CRITICAL"`, `"BLOCKED"`.
- **`reason`**: A descriptive string explaining why the decision was reached.
- **`approval_method`**: The method required or used to approve (e.g., `"none"`, `"cli_confirm"`, `"passphrase"`, `"delegation"`).

### Optional / Conditional Fields:
- **`approval_request_id`**: A unique string UUID generated if the request remains pending user approval.
- **`approval_command`**: The command the user must run to approve the request (e.g., `"agent-sudo approve <id>"`).
- **`approval_expires_at`**: ISO 8601 UTC timestamp when the pending request expires.
- **`approval_expires_in_seconds`**: An integer indicating the remaining TTL.

### JSON Schema Specification:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "PolicyDecision",
  "type": "object",
  "properties": {
    "decision": {
      "type": "string",
      "enum": ["ALLOW", "DENY", "REQUIRE_APPROVAL", "REQUIRE_STRONG_APPROVAL"]
    },
    "classification": {
      "type": "string",
      "enum": ["SAFE", "SENSITIVE", "CRITICAL", "BLOCKED"]
    },
    "reason": {
      "type": "string"
    },
    "approval_method": {
      "type": "string"
    },
    "approval_request_id": {
      "type": "string",
      "format": "uuid"
    },
    "approval_command": {
      "type": "string"
    },
    "approval_expires_at": {
      "type": "string",
      "format": "date-time"
    },
    "approval_expires_in_seconds": {
      "type": "integer",
      "minimum": 30,
      "maximum": 600
    }
  },
  "required": ["decision", "classification", "reason", "approval_method"]
}
```

---

## 3. AuditRecord Schema

An `AuditRecord` represents a logged security event. It captures the action request, the policy decision, and cryptographic integrity parameters.

### Required Fields:
- **`timestamp`**: ISO 8601 UTC timestamp format (`YYYY-MM-DDTHH:MM:SSZ`).
- **`event_type`**: The type of logged event (e.g., `"gateway_decision"`, `"passphrase_reset"`, `"delegation_create"`).
- **`request`**: An object containing the target action parameters:
  - `actor`: string
  - `source`: string
  - `tool`: string
  - `action`: string
  - `target`: string
  - `payload_summary`: string
  - `source_trust`: string (`"USER_DIRECT"`, `"AGENT_INTERNAL"`, `"EXTERNAL_CONTENT"`, or `"UNKNOWN"`)
- **`decision`**: The decision string (matching `PolicyDecision`).
- **`classification`**: The classification string (matching `PolicyDecision`).
- **`reason`**: A descriptive string explaining the audit outcome.
- **`approval_method`**: The approval method utilized.
- **`previous_hash`**: The SHA-256 hash of the immediately preceding line in the audit log. If this is the first entry (genesis), it must be `64` zeros (`"0000000000000000000000000000000000000000000000000000000000000000"`).
- **`entry_hash`**: The SHA-256 hash computed for the current entry (see Section 4).

### JSON Schema Specification:
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AuditRecord",
  "type": "object",
  "properties": {
    "timestamp": { "type": "string", "format": "date-time" },
    "event_type": { "type": "string" },
    "request": {
      "type": "object",
      "properties": {
        "actor": { "type": "string" },
        "source": { "type": "string" },
        "tool": { "type": "string" },
        "action": { "type": "string" },
        "target": { "type": "string" },
        "payload_summary": { "type": "string" },
        "source_trust": { "type": "string", "enum": ["USER_DIRECT", "AGENT_INTERNAL", "EXTERNAL_CONTENT", "UNKNOWN"] }
      },
      "required": ["actor", "source", "tool", "action", "target", "payload_summary", "source_trust"]
    },
    "decision": { "type": "string", "enum": ["ALLOW", "DENY", "REQUIRE_APPROVAL", "REQUIRE_STRONG_APPROVAL"] },
    "classification": { "type": "string", "enum": ["SAFE", "SENSITIVE", "CRITICAL", "BLOCKED"] },
    "reason": { "type": "string" },
    "approval_method": { "type": "string" },
    "previous_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "entry_hash": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
  },
  "required": [
    "timestamp",
    "event_type",
    "request",
    "decision",
    "classification",
    "reason",
    "approval_method",
    "previous_hash",
    "entry_hash"
  ]
}
```

---

## 4. Cryptographic Hash-Chaining Verification

To detect log deletion or tampering in local user files, records are appended sequentially to a JSONL log file. Each line contains a hash that links to the previous line.

### Hashing Steps:
1. **Extract Entry**: Copy the audit record object.
2. **Remove Target Hash**: Remove the `entry_hash` key from the object (if present).
3. **Canonicalize**: Serialize the remaining keys into a sorted, compact JSON string:
   - Sort keys alphabetically.
   - Use double quotes for strings.
   - Use minimal separators (no whitespaces after `:` and `,`).
   - Encode string as UTF-8.
4. **Concatenate**: Concatenate the `previous_hash` string value directly with the canonical JSON string.
5. **Hash**: Calculate the SHA-256 checksum of the concatenated bytes.
6. **Represent**: Output the hash as a 64-character lowercase hexadecimal string.

#### Formula:
$$entry\_hash = \text{SHA256}(\text{previous\_hash} + \text{canonical\_json}(\text{record} \setminus \{\text{"entry\_hash"}\}))$$

---

## 5. Specification Scope vs. Runtime Support

| Category | Defined in Specification (Universal) | Managed by Runtime/Library (Sudo Gateway) |
| :--- | :--- | :--- |
| **Data Formats** | `PolicyDecision` & `AuditRecord` schemas. | Parsing YAML policies, checking environment overrides. |
| **Audit Trails** | Hash-chain calculation & canonicalization. | File access, locking logs, exporting to external pipelines. |
| **Approvals** | Status states & validation conditions. | Storing pending files, prompting operator TTY, verifying passphrases. |
| **Delegations**| Token matching structures & scopes. | Thread-safe DB/JSON persistence, decrementing usage counters. |

### Gateway-Specific Details
The stdio MCP wrapper protocols, prompt override phrase lists, console CLI prompts, and OS credential storage setups are kept gateway-specific and are not part of the standard core specification.

---

## 6. Compatibility Path for Single-Process Apps (LexFlow)

External single-process tools like LexFlow that run in-process can align with `Agent_Sudo` formats without requiring a background daemon:

1. **Direct Audit Output**:
   Instead of calling `agent-sudo-mcp`, LexFlow can implement the canonical hash-chain algorithm to log tool outcomes directly into `~/.agent-sudo/mcp-audit.jsonl` (or a dedicated audit file). This enables unified audits using `agent-sudo verify-audit`.
2. **Shared Delegation Checking**:
   LexFlow can read `~/.agent-sudo/delegations.json` directly. When it executes a tool, it can match the action against active tokens, decrementing uses inside the JSON file safely.
3. **Common Action Schema**:
   LexFlow can map its internal desktop workflow actions to the standard target fields defined in `ActionRequest`.
