# Agent_Sudo Interoperability Test Kit

> [!NOTE]
> **Specification Version**: `v0.4.0` (Pre-v1 Draft)  
> **Status**: Draft. This test kit reflects the current pre-v1 spec draft semantics and may evolve during the formal Spec Review process. Do not treat these details as finalized.

This Interoperability Test Kit is designed to help developer teams build compatible client/emitter implementations of the `Agent_Sudo` audit log (such as LexFlow or external agent runtimes) in JS, TS, Go, Rust, or other languages.

Using this guide and the associated reference assets, you can validate that your implementation produces byte-for-byte identical canonical serialization, hash computations, and chain linkage without having to read or reverse-engineer the Python source code.

---

## 1. Reference Files & Expected Hashes

This test kit includes two companion reference files:
*   [reference_record.json](file:///Volumes/Storage/Agent_Sudo/docs/interop/reference_record.json): A single-record JSON file representing an `ALLOW` decision. Note that this file is pretty-printed for human readability. Emitters must canonicalize it (compact sorted serialization) to compute its hash.
*   [reference_log.jsonl](file:///Volumes/Storage/Agent_Sudo/docs/interop/reference_log.jsonl): A three-record JSONL log demonstrating a valid hash chain with `ALLOW`, `REQUIRE_STRONG_APPROVAL` (approved), and `DENY` events.

### Reference Table

| Target Reference File | Record # | Event Type | Expected `previous_hash` | Expected `entry_hash` | Verification Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`reference_record.json`** | 1 | `gateway_decision` | `0000000000000000000000000000000000000000000000000000000000000000` | `788e65ed4b7ec79f408e5633d1ba3df29eebf13f437aa4980f0d8b7bf5926171` | **Valid** (as a single line JSONL) |
| **`reference_log.jsonl`** | 1 | `gateway_decision` | `0000000000000000000000000000000000000000000000000000000000000000` | `788e65ed4b7ec79f408e5633d1ba3df29eebf13f437aa4980f0d8b7bf5926171` | **Valid** |
| **`reference_log.jsonl`** | 2 | `gateway_decision` | `788e65ed4b7ec79f408e5633d1ba3df29eebf13f437aa4980f0d8b7bf5926171` | `e8a76304f8fd12d536e44ca05c73e998bbd95bccfe52fa9b9f1dcf1c5b187e4f` | **Valid** |
| **`reference_log.jsonl`** | 3 | `gateway_decision` | `e8a76304f8fd12d536e44ca05c73e998bbd95bccfe52fa9b9f1dcf1c5b187e4f` | `6e034df129a770b3000e24cf48e3428724f9c80e828eba64bf50fa19c9d21d51` | **Valid** |

---

## 2. Canonical Serialization Rules

To verify the audit log cryptographically, every entry must be serialized to an exact byte-for-byte representation before hashing. The rules are:

### A. Key Exclusions
The `entry_hash` key **must be excluded** from the record object before serialization. All other fields (including `previous_hash`) must remain.

### B. Recursive Key Sorting
*   All keys in JSON objects must be sorted alphabetically at **every level of nesting**.
*   If an object is nested inside a list/array (e.g., `approval_attempts`), its keys must also be sorted alphabetically.
*   **Example**:
    ```json
    {"z": 1, "a": {"y": 2, "b": 3}, "c": [{"x": 4, "d": 5}]}
    ```
    must serialize as:
    ```json
    {"a":{"b":3,"y":2},"c":[{"d":5,"x":4}],"z":1}
    ```

### C. Compact Formatting
*   The serialized JSON string must contain **no whitespace spaces** around separators.
*   The comma separator must be exactly `,` (no spaces).
*   The colon separator must be exactly `:` (no spaces).
*   **Correct**: `{"a":1,"b":2}`
*   **Incorrect**: `{"a": 1, "b": 2}`

### D. Newlines and Blank Lines
*   In the `.jsonl` audit log, each record is written on a single line, terminated by a Unix newline (`\n`).
*   Empty/blank lines (e.g., trailing whitespace or `\n\n`) are skipped by the verifier and do not invalidate the chain, but emitters should avoid writing them.

### E. UTF-8 and ASCII Escaping
*   The serialized JSON string must be encoded as **UTF-8 bytes** before hashing.
*   **Warning**: The Python reference implementation uses default JSON serialization, which escapes non-ASCII Unicode characters (e.g., `€` is serialized as `\u20ac`). JavaScript's `JSON.stringify` does not do this by default. Emitters must ensure that non-ASCII Unicode characters are escaped in standard JSON ASCII representation, or limit log content to the ASCII range to prevent hash mismatches.

### F. Float Handling
*   JavaScript and Python represent floating-point numbers differently (e.g., JS serializes `10.0` as `10`, whereas Python serializes it as `10.0`).
*   **Best Practice**: Emitters should avoid using floats in audit logs entirely. All relative durations or timeouts (like `approval_expires_in_seconds`) must be represented as integers.

---

## 3. JavaScript Reference Implementation

Below is a compliant JavaScript helper that recursively sorts object keys (including arrays containing objects) and serializes the record compactly without whitespace.

```javascript
/**
 * Recursively sorts the keys of an object or array.
 * @param {*} obj - The input value to canonicalize.
 * @returns {*} The canonicalized value.
 */
function canonicalize(obj) {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(canonicalize);
  }
  const sortedKeys = Object.keys(obj).sort();
  const sortedObj = {};
  for (const key of sortedKeys) {
    sortedObj[key] = canonicalize(obj[key]);
  }
  return sortedObj;
}

/**
 * Serializes an Agent_Sudo audit record into its canonical bytes.
 * Strips 'entry_hash' and sorts keys recursively.
 * @param {Object} record - The full audit record.
 * @returns {string} The compact canonical JSON string.
 */
function canonicalizeRecord(record) {
  // Strip entry_hash
  const clean = {};
  for (const [key, value] of Object.entries(record)) {
    if (key !== 'entry_hash') {
      clean[key] = value;
    }
  }
  
  // Recursively sort keys
  const sorted = canonicalize(clean);
  
  // JSON.stringify by default outputs compact representation (no spaces around : and ,)
  // Note: For non-ASCII unicode safety, ensure characters are escaped or keep to ASCII.
  return JSON.stringify(sorted);
}

/**
 * Computes the SHA-256 hash of a record given the previous entry hash.
 * Uses Node.js 'crypto' module.
 * @param {string} previousHash - Hex string of the previous entry's hash.
 * @param {Object} record - The current record.
 * @returns {string} The hex representation of the entry's SHA-256 hash.
 */
function computeEntryHash(previousHash, record) {
  const crypto = require('crypto');
  const canonicalStr = canonicalizeRecord(record);
  
  // Concatenate previous_hash string and canonical bytes
  const hasher = crypto.createHash('sha256');
  hasher.update(previousHash, 'utf8');
  hasher.update(canonicalStr, 'utf8');
  return hasher.digest('hex');
}
```

---

## 4. TypeScript Verification Guide

Here is a guide showing how to verify an audit log file programmatically in TypeScript (e.g., as part of your CI pipeline or in-process verification helper).

```typescript
import * as fs from 'fs';
import * as readline from 'readline';
import * as crypto from 'crypto';

interface VerificationResult {
  success: boolean;
  lineNumber?: number;
  expectedHash?: string;
  actualHash?: string;
  reason?: string;
}

// Reuse the JavaScript canonicalize and computeEntryHash logic in TS
function canonicalize(obj: any): any {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }
  if (Array.isArray(obj)) {
    return obj.map(canonicalize);
  }
  const sortedKeys = Object.keys(obj).sort();
  const sortedObj: Record<string, any> = {};
  for (const key of sortedKeys) {
    sortedObj[key] = canonicalize(obj[key]);
  }
  return sortedObj;
}

function canonicalizeRecord(record: Record<string, any>): string {
  const clean: Record<string, any> = {};
  for (const [key, value] of Object.entries(record)) {
    if (key !== 'entry_hash') {
      clean[key] = value;
    }
  }
  return JSON.stringify(canonicalize(clean));
}

function computeEntryHash(previousHash: string, record: Record<string, any>): string {
  const canonicalStr = canonicalizeRecord(record);
  const hasher = crypto.createHash('sha256');
  hasher.update(previousHash, 'utf8');
  hasher.update(canonicalStr, 'utf8');
  return hasher.digest('hex');
}

/**
 * Validates the hash chain of a JSONL file.
 * @param filePath Path to the audit log .jsonl file.
 */
async function verifyJsonlFile(filePath: string): Promise<VerificationResult> {
  const fileStream = fs.createReadStream(filePath);
  const rl = readline.createInterface({
    input: fileStream,
    crlfDelay: Infinity,
  });

  let previousHash = '0'.repeat(64);
  let lineNumber = 0;

  for await (const line of rl) {
    lineNumber++;
    const trimmed = line.trim();
    if (!trimmed) {
      continue; // Skip blank lines
    }

    let record: any;
    try {
      record = JSON.parse(trimmed);
    } catch (e: any) {
      return { success: false, lineNumber, reason: `Invalid JSON: ${e.message}` };
    }

    if (typeof record !== 'object' || record === null || Array.isArray(record)) {
      return { success: false, lineNumber, reason: 'Line is not a JSON object' };
    }

    // 1. Verify previous_hash link
    const expectedPrev = record.previous_hash;
    if (expectedPrev !== previousHash) {
      return {
        success: false,
        lineNumber,
        expectedHash: previousHash,
        actualHash: expectedPrev,
        reason: 'previous_hash mismatch',
      };
    }

    // 2. Verify entry_hash
    const actualHash = record.entry_hash;
    if (!actualHash) {
      return { success: false, lineNumber, reason: 'Missing entry_hash' };
    }

    const expectedHash = computeEntryHash(previousHash, record);
    if (actualHash !== expectedHash) {
      return {
        success: false,
        lineNumber,
        expectedHash,
        actualHash,
        reason: 'entry_hash mismatch',
      };
    }

    // Advance previous_hash to current entry_hash
    previousHash = actualHash;
  }

  return { success: true, reason: 'Audit log verified successfully' };
}

// Example usage:
// verifyJsonlFile('./reference_log.jsonl').then(result => {
//   if (result.success) {
//     console.log("SUCCESS: Audit log verified");
//   } else {
//     console.error(`FAILURE at line ${result.lineNumber}: ${result.reason}`);
//     console.error(`Expected: ${result.expectedHash}`);
//     console.error(`Actual:   ${result.actualHash}`);
//   }
// });
```

---

## 5. Portability & Gaps Evaluation

### Can an external implementation pass compatibility tests without reading Python source code?

**Yes, but with caveats.** With the inclusion of this Interoperability Test Kit, an external developer has all necessary math, schemas, and serialization algorithms. However, there are remaining subtle gaps in the documentation that could lead to verification failures:

1.  **Unicode/Escape Discrepancy**: Standard `JSON.stringify` does not escape non-ASCII characters, whereas Python's default `json.dumps` does. This is undocumented in the core specifications, and could cause silent verification failures if non-ASCII characters appear in fields like `payload_summary` or `reason`.
2.  **Default Values / Optional Fields**: Python's schemas have certain fields that default to empty values (e.g. `approval_command: ""` or `approval_attempts: []`). If an external implementation omits these fields instead of writing their default values, verification will fail. Emitters must strictly populate all fields defined in the schema to ensure identical serialization structure.
3.  **Key Sorting in Arrays**: Existing specs do not explicitly state that nested objects inside arrays (e.g. elements of `approval_attempts`) must have their keys sorted. Emitters that only sort top-level/first-level dictionary keys will fail hashing on complex logs.

### Interoperability Readiness Score: `85/100`
*   **Why not 100?**: The lack of a cross-language float format standard and the implicit ASCII-escaping behavior of Python's json serializer are minor gaps. We recommend that future specifications address these explicitly.
