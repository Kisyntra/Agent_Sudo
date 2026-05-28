# Specification: Canonical Hash Chain and Verifier Contract

This document provides a strict, implementation-independent specification of `Agent_Sudo` canonical serialization, cryptographic hash chaining, and verifier compatibility boundaries. Adherence to this specification ensures that two independent codebases (e.g., `Agent_Sudo` and `LexFlow`) compute identical hashes for identical audit events.

---

## 1. Canonical Serialization Rules

To ensure that different JSON libraries produce byte-identical strings for equivalent JSON objects, the serialization must follow these strict rules:

### A. Key Sorting
- All object keys at all levels of nesting **must** be sorted alphabetically in lexicographical order (using Unicode/UTF-16 codepoint values).
- Arrays **must** preserve their original order; their elements must not be sorted.

### B. Whitespace Handling
- No whitespace is allowed outside of string literals.
- **Key-Value Separator**: Must be a single colon without surrounding spaces (`:`).
- **Element Separator**: Must be a single comma without surrounding spaces (`,`).
- **Incorrect**: `{"actor" : "mcp", "tool" : "shell"}`
- **Correct**: `{"actor":"mcp","tool":"shell"}`

### C. Character Escaping
- Strings **must** be enclosed in double quotes (`"`).
- Special characters inside strings **must** be escaped as follows:
  - Double quote: `\"`
  - Backslash: `\\`
  - Newline: `\n`
  - Carriage return: `\r`
  - Tab: `\t`

### D. Numbers Formatting
- Integers **must** be serialized in standard base-10 representation without leading zeros (except for the number `0` itself).
- Floating-point values should be avoided in audit records. If required, they must use standard decimal formats without trailing decimal zeros or exponent forms unless specified.

### E. UTF-8 Encoding
- The resulting canonical JSON string **must** be encoded as a raw, standard UTF-8 byte stream before hashing.

---

## 2. Cryptographic Hash Chain Computation

Each entry in the log links to the previous entry, creating a tamper-evident audit trail.

### Step 1: Input Extraction
Given an audit record object:
1. Copy the record.
2. Remove the `"entry_hash"` key from the copied object.

### Step 2: Canonicalization
Serialize the remaining record object to a UTF-8 encoded byte stream according to the **Canonical Serialization Rules** in Section 1. Let this byte stream be $C$.

### Step 3: Concatenation
Retrieve the `"previous_hash"` string from the record (representing the hex hash of the preceding line). Concatenate the bytes of the `previous_hash` string with $C$:
$$\text{input\_bytes} = \text{previous\_hash}.encode(\text{"utf-8"}) + C$$

### Step 4: SHA-256 Hashing
Compute the SHA-256 checksum of the concatenated byte stream:
$$\text{entry\_hash} = \text{HexEncode}(\text{SHA-256}(\text{input\_bytes}))$$
The result is represented as a 64-character lowercase hexadecimal string.

### Genesis Record Behavior
For the first record in the audit log file, the `previous_hash` **must** be set to a string of 64 zeros:
`"0000000000000000000000000000000000000000000000000000000000000000"`

### Bytes-on-Disk Expectations
- **Format**: JSON Lines (JSONL). One JSON object per line.
- **Line Ending**: Each record line must end with a single Unix newline character (`\n`). Carriage returns (`\r\n`) must be normalized to `\n` on read.
- **Trailing Newline**: The file must have a single trailing newline at the end of the file.

---

## 3. Evaluation of the Reference Verifier

The current verification routine `verify_audit_log` in `agent_sudo/audit.py` reads a file path and checks the chain. 

### Internal Assumptions
- **Synchronous File IO**: Assumes a local filesystem path.
- **Python Stdlib JSON Serialization**: Relies on `json.dumps(sort_keys=True, separators=(',', ':'))` which naturally matches our canonical rules, but might differ from other languages' standard parsers (e.g. if they handle escapes or key ordering differently).

### Reusable Verifier Boundaries (Proposed Helpers)
To support in-process verification, we propose a stateless library helper module (`agent_sudo.spec_helpers`) that abstracts verification:

```python
import hashlib
import json

def canonicalize_record(record: dict) -> str:
    """Serializes a record canonically, excluding the entry_hash key."""
    clean = {k: v for k, v in record.items() if k != "entry_hash"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))

def compute_entry_hash(previous_hash: str, record: dict) -> str:
    """Computes the SHA-256 entry hash using canonical rules."""
    canonical_str = canonicalize_record(record)
    concatenated = f"{previous_hash}{canonical_str}"
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()

def verify_hash_chain(records: list[dict]) -> tuple[bool, str]:
    """Validates the hash chain sequence of a list of record objects."""
    previous_hash = "0" * 64
    for index, record in enumerate(records, start=1):
        expected_prev = record.get("previous_hash")
        if expected_prev != previous_hash:
            return False, f"record {index}: previous_hash mismatch"
        actual_hash = record.get("entry_hash")
        expected_hash = compute_entry_hash(previous_hash, record)
        if actual_hash != expected_hash:
            return False, f"record {index}: entry_hash mismatch"
        previous_hash = actual_hash
    return True, "verification succeeded"
```

*This stateless code is highly portable, has no filesystem dependencies, and can be directly used in embedded runtimes.*

---

## 4. External Compatibility Requirements

For external applications (like LexFlow) to produce compatible audit records:

### A. Minimal Required AuditRecord Fields
Every entry **must** contain:
- `timestamp`: string (ISO 8601 UTC)
- `event_type`: string
- `request`: object (with `actor`, `source`, `tool`, `action`, `target`, `payload_summary`, `source_trust`)
- `decision`: string
- `classification`: string
- `reason`: string
- `approval_method`: string
- `previous_hash`: string
- `entry_hash`: string

### B. Optional Extension Fields
Integrations are encouraged to add custom top-level keys to represent platform-specific metadata (e.g., `"lexflow_workflow_id"`, `"session_metadata"`).

### C. Forward Compatibility and Unknown Fields
- **Policy Decoders**: When parsing decision records, engines **must ignore** unknown fields to prevent runtime failures.
- **Hashing Log Verification**: During canonical serialization and hash chain calculation, engines **must include all fields** (including unknown extension keys) exactly as they are written in the JSON. This ensures the cryptographic integrity checks verify successfully across different runtimes.

---

## 5. Strategic Recommendation

### Stability Assessment
The verifier semantics (Genesis base, sorted-key serialization, SHA-256 concatenation) are **highly stable** and ready for external adoption. Because the mathematical chain verification has zero dependency on specific OS layers or gateway internals, external systems can implement it with absolute confidence.

We recommend **publishing these specifications immediately** as stable boundaries for the ecosystem, while keeping the full Python in-process engine implementation deferred.
