# PydanticAI Integration — Real End-to-End Dogfood

This is the canonical example of embedding the **Agent_Sudo authorization engine**
inside a real agent loop. It runs the full path and verifies the result:

```
PydanticAI agent
  → PermissionGateway        (real classification + provenance-aware decision)
  → real local file action    (actual read / write in a temp dir)
  → approval / delegation     (real scoped delegation token)
  → audit log                 (real hash-chained JSONL)
  → audit verification        (real chain verification)
```

## What this example exercises

| Part | Real? | Notes |
| :--- | :--- | :--- |
| **Model** | Deterministic test double | PydanticAI `FunctionModel` scripts which tool runs with which arguments. No LLM, no API key, no network. |
| **Enforcement / decisions** | Yes | Real `PermissionGateway`: classification, provenance escalation, ALLOW / REQUIRE_APPROVAL / DENY. |
| **File I/O** | Yes | Tools perform actual `Path.read_text` / `Path.write_text` in a temp dir. |
| **Approval via delegation** | Yes | A real scoped, single-use `DelegationToken` authorizes the gated write. |
| **Audit + verification** | Yes | Real hash-chained audit log; verified with `verify_audit_log` at the end. |

All state lives in a `TemporaryDirectory`. The example never touches `~/.agent-sudo`.

## Run it

```bash
pip install -e ".[examples]"
python examples/pydantic_ai/example.py
```

Expected output:

```
1. Safe read (USER_DIRECT)        -> hello from disk
2a. Sensitive write, no delegation -> REQUIRE_APPROVAL: not executed (CLI_CONFIRM)
2b. Sensitive write, delegated     -> ALLOW: wrote report.txt via DELEGATION
3. Blocked exfiltration            -> DENY: blocked by policy

4. Audit: 4 records, chain verified

Self-check passed: enforcement path behaved exactly as intended.
```

The script exits non-zero if any scenario deviates (e.g. a held action ran, or
the audit chain failed to verify), so it doubles as a self-test.

## The scenarios

1. **USER_DIRECT safe action.** A properly attested `read_file` → `ALLOW` → the
   tool performs a real read and returns the file's actual contents.
2. **Sensitive action requiring authorization.**
   - *2a — held:* a `write_file` with no delegation → `REQUIRE_APPROVAL`. The
     gate does **not** treat that as allow — the file is **not** written.
   - *2b — delegated:* after a scoped `DelegationToken` is granted for that path,
     the same write → `ALLOW` (method `DELEGATION`) → the file is really written.
3. **Blocked action.** An `exfiltrate_secrets` attempt → `DENY`. The tool never
   performs the upload.
4. **Audit verification.** After all scenarios, the hash-chained audit log is
   verified intact.

## The integration pattern

The reusable piece is the `gate(...)` helper: build an attested `ActionRequest`,
call `gateway.evaluate(request)`, and **proceed only when the decision is
`ALLOW`**. Wrap each real tool with it. That is the whole integration — the
engine decides, your tool executes only when permitted, and every decision is
audited.
