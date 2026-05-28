# Schema Versioning Proposal

This document outlines the versioning philosophy, compatibility guarantees, and migration strategies for `Agent_Sudo` governance schemas.

---

## 1. Versioning Philosophy

To support interoperability across external integrations (such as `LexFlow`), the governance schemas (Layer 1) are versioned independently of the reference gateway software (Layer 2).
- **Gateway Versioning**: Follows standard Semantic Versioning (`MAJOR.MINOR.PATCH`) reflecting features, command line updates, and code changes in the reference implementation.
- **Schema Specification Versioning**: Follows its own Semantic Versioning. A schema release is represented in the namespace or as a document attribute (e.g., `schema_version: "1.0.0"`).
  - **PATCH**: Non-breaking description adjustments, comment updates, or string validation regex refinements.
  - **MINOR**: Adding optional fields to inputs/outputs or introducing new non-breaking states.
  - **MAJOR**: Removing required fields, changing type assertions, or altering the cryptographic hash-chain algorithm.

---

## 2. Compatibility Guarantees

We enforce strict rules to prevent client breakage when schemas update:

```
                  +-----------------------------------+
                  |      COMPATIBILITY BOUNDS         |
                  +-----------------------------------+
                                    |
            +-----------------------+-----------------------+
            |                                               |
            v                                               v
+-----------------------+                       +-----------------------+
|  FORWARD-COMPATIBLE   |                       |  BACKWARD-COMPATIBLE  |
|  - Older engines MUST |                       |  - Newer engines MUST |
|    ignore unknown     |                       |    accept and parse   |
|    JSON keys.         |                       |    older schemas.     |
+-----------------------+                       +-----------------------+
```

### Forward Compatibility
Older versions of the gateway must remain capable of parsing requests sent by newer clients:
- **Rule of Extension**: Clients may append new fields. Gates/runtimes must ignore unrecognized keys instead of rejecting the payload with a schema parsing error.
- **Nullable Defaults**: Newly added fields in requests must be optional and have sane default behaviors.

### Backward Compatibility
Newer engines and specifications must remain capable of reading older data files:
- **No Field Deletion**: Required fields in `ActionRequest`, `PolicyDecision`, or `AuditRecord` cannot be removed or renamed in minor schema updates.
- **Stable Hash Canonicalization**: The fields included in the cryptographic hash-chain canonical serialization must remain stable to prevent breaking verification of historical logs.

---

## 3. Experimental vs. Stable Schemas

To facilitate rapid innovation without destabilizing production deployments, we define two schema namespaces:

| Schema Tier | Namespace / Path Indicator | Compatibility Guarantees | Lifecycle Phase |
| :--- | :--- | :--- | :--- |
| **Experimental** | `v1alpha`, `v1beta` | None. Fields can be mutated or removed in minor updates. | Used for design exploration and early integration validation. |
| **Stable** | `v1` (e.g., `schema_version: "1.0"`) | Strict forward and backward compatibility. No breaking changes. | Used in production systems and committed API specifications. |

---

## 4. Migration Strategy

When major schema updates occur, the gateway implements migration paths to minimize disruption:

1. **Parser Version Routing**:
   The input payload is inspected for a version key (e.g., `"schema_version"`). The engine routes the dictionary to the corresponding schema parser:
   ```python
   def parse_request(data: dict) -> ActionRequest:
       version = data.get("schema_version", "1.0.0")
       if version.startswith("1."):
           return parse_v1_request(data)
       elif version.startswith("2."):
           return parse_v2_request(data)
       raise ValueError(f"Unsupported schema version: {version}")
   ```
2. **Translation Layers (Adapters)**:
   For database/state files (like `delegations.json` or `config.json`), the runtime auto-migrates files to the latest version on write.
3. **Audit Log Continuity**:
   If the hash chain canonicalization algorithm changes (e.g., upgrading from SHA-256 to SHA-3), the audit verification tool must support a transition marker in the log. Entries preceding the marker verify with the older algorithm, while subsequent entries verify with the newer algorithm.
