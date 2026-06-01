# Implementation Plan — Fail-Closed Provenance Defaults

**Type:** Plan only. No code in this document.
**Goal:** Unify missing-provenance defaults so all entry paths fail closed to `UNKNOWN` instead of `USER_DIRECT`. Absent provenance ⇒ untrusted. Explicit `USER_DIRECT` is preserved **only** when the caller actually provides it.

**Out of scope (per constraints):** host signatures, nonce binding, provenance redesign, removing fields, target/path-blocking changes. Forged `USER_DIRECT` is explicitly **not** solved here — it is pinned as a documented limitation.

---

## 1. The four default sites (and the one that's already correct)

| # | Site | Current default when provenance absent | Path type | Real runtime? | Action |
|---|------|----------------------------------------|-----------|---------------|--------|
| S1 | [`mcp_validation.py:60-61`](../../agent_sudo/mcp_validation.py) `tool_call_from_jsonrpc` | `source="user"`, `source_trust="USER_DIRECT"` | wire (JSON-RPC) | **YES** — used by [`mcp_server.py:102`](../../agent_sudo/mcp_server.py) | **FIX (required)** |
| S2 | [`models.py:144-147`](../../agent_sudo/models.py) `ActionRequest.from_dict` else-branch | `source_trust = TrustLevel.USER_DIRECT` | wire (JSON dict) | **YES** — used by [`gateway.py:420`](../../agent_sudo/gateway.py) batch eval | **FIX (required)** |
| S3 | [`models.py:126`](../../agent_sudo/models.py) `ActionRequest.source_trust` dataclass field default | `= TrustLevel.USER_DIRECT` | programmatic constructor | indirect | **FIX (recommended — §3 footgun)** |
| S4 | [`builders.py`](../../agent_sudo/builders.py) ×8 static methods | `source_trust: … = TrustLevel.USER_DIRECT` | SDK convenience API | example/SDK | **FIX (recommended, with carve-out)** |
| — | [`adapters/common.py:280-300`](../../agent_sudo/adapters/common.py) `_source_trust` | already falls back to `UNKNOWN` | wire (MCP/native) | YES | **NO CHANGE — already fail-closed** |

The adapter path (`normalize_tool_call`) is the reference behavior we are unifying everyone else toward. Note S1 feeds *into* the adapter path but pre-stamps `source_trust="USER_DIRECT"`, which the adapter then honors as an explicit value — so S1's default defeats the adapter's safe fallback. That is the single most important fix.

---

## 2. Exact behavior — before / after

### S1 — `mcp_validation.tool_call_from_jsonrpc` (live MCP boundary)

**Before:** a JSON-RPC `tools/call` with no `source`/`source_trust` fields (the normal case from clients like Claude Desktop) is stamped `source="user"`, `source_trust="USER_DIRECT"`. A `read_file` → ALLOW; trust escalation never triggers.

**After:** absent fields default to `source="unknown"`, `source_trust="UNKNOWN"`. Same `read_file` → classified SENSITIVE → `REQUIRE_APPROVAL`. A client that *does* send `"source_trust": "USER_DIRECT"` is unchanged.

> Change: line 60 default `"user"` → `"unknown"`; line 61 default `"USER_DIRECT"` → `"UNKNOWN"`. (Two string-literal defaults; no logic change.)

### S2 — `ActionRequest.from_dict` else-branch

**Before:**
```
if "source_trust" in data:        -> use it           (explicit: preserved)
elif provenance_data:             -> derive from provenance
else:                             -> USER_DIRECT       ← fail-open
```

**After:** the `else` yields `TrustLevel.UNKNOWN`. The two preceding branches are untouched, so explicit `source_trust` and provenance-derived trust behave exactly as today.

> Change: line 147 `TrustLevel.USER_DIRECT` → `TrustLevel.UNKNOWN`. (One token.)

### S3 — `ActionRequest` dataclass field default

**Before:** `source_trust: TrustLevel = TrustLevel.USER_DIRECT`. Any `ActionRequest(...)` built without `source_trust=` is fully trusted by default — the §3 footgun for future adapters/callers.

**After:** `source_trust: TrustLevel = TrustLevel.UNKNOWN`. Constructors that mean "trusted user" must say `source_trust=TrustLevel.USER_DIRECT` explicitly (consistent with the stated principle: preserve explicit USER_DIRECT only where provided).

> Change: line 126 default `TrustLevel.USER_DIRECT` → `TrustLevel.UNKNOWN`. **This is the churn-bearing change** (see §5).

### S4 — `builders.py` (`AgentActionRequest.*`)

**Before:** every builder defaults `source_trust=TrustLevel.USER_DIRECT` (and `source="user"`).

**After (recommended):** default `source_trust=TrustLevel.UNKNOWN`. Callers that intend a trusted user action pass `source_trust=TrustLevel.USER_DIRECT`.

> **Carve-out option:** if the builders are meant as an explicit "this is the operator's own action" convenience, keeping their `USER_DIRECT` default is defensible *because the developer is the trusted party authoring the call*. If you take this option, document it inline and in the threat-model doc so it is a stated choice, not an accident. The plan's default recommendation is to flip them for consistency; the carve-out is acceptable if explicitly noted. **Decide one and record it.**

### Net classifier effect (all sites)

Only **SAFE** actions change outcome: SAFE + (absent trust ⇒ `UNKNOWN`) now escalates SAFE→SENSITIVE at [`classifier.py:107`](../../agent_sudo/classifier.py) (`source_trust in {EXTERNAL_CONTENT, UNKNOWN}`). SENSITIVE/CRITICAL/BLOCKED actions are unaffected — their classification never depended on the absent-trust default. So the behavioral delta is precisely: *"a SAFE action with no stated provenance now asks for approval instead of running silently."*

---

## 3. Affected files

**Code (4 files):**
- `agent_sudo/mcp_validation.py` — S1 (2 default literals)
- `agent_sudo/models.py` — S2 (else-branch) + S3 (field default)
- `agent_sudo/builders.py` — S4 (8 signatures; or document carve-out)

**Docs (2 files):**
- `docs/architecture/security_model.md` — add a short "Default trust posture" note: missing/unparseable provenance is treated as `UNKNOWN` (untrusted) and escalated; explicit `USER_DIRECT` is honored as-is and remains forgeable (link to the provenance audit).
- `README.md` — one line in the existing **What Agent_Sudo Protects / Does Not Protect** section: "Actions arriving without trustworthy provenance are treated as **unknown/untrusted** and require approval, not allowed by default."

**Tests (1 new file + small touch-ups):**
- `tests/test_failclosed_provenance.py` — new (see §4)
- Touch-ups to existing tests that relied on the implicit `USER_DIRECT` for a SAFE action (see §5 for the enumeration step).

---

## 4. Regression tests to add

New file `tests/test_failclosed_provenance.py`:

**T1 — missing provenance escalates (does not get full trust).** Two assertions, one per wire path:
- `tool_call_from_jsonrpc` with a SAFE call and no `source`/`source_trust` → run through the gateway → assert decision is `REQUIRE_APPROVAL`, **not** `ALLOW`.
- `ActionRequest.from_dict({...read_file..., no source_trust, no provenance})` → assert `.source_trust == TrustLevel.UNKNOWN`.

**T2 — adapter path and model path are consistent.** Construct the same logical "SAFE read with absent provenance" via both `from_mcp_tool_call(...)` (adapter) and `ActionRequest.from_dict(...)` (model). Assert both yield `source_trust == TrustLevel.UNKNOWN` **and** both classify to SENSITIVE / `REQUIRE_APPROVAL`. (This is the regression guard against the two paths drifting again.)

**T3 — forged `USER_DIRECT` is still honored (documented limitation, not solved here).** Construct a tool call from an obviously external source but with explicit `source_trust="USER_DIRECT"`; assert it is **still trusted** (SAFE→ALLOW). Name it explicitly, e.g. `test_forged_user_direct_is_still_trusted_known_limitation`, with a docstring stating this pins current behavior and is intentionally out of scope for this PR (the fix is host-stamped provenance / nonce binding, tracked separately). This both documents the boundary and gives a future fix a target to flip.

**T4 — explicit `USER_DIRECT` is preserved (no over-correction).** `ActionRequest.from_dict({..., "source_trust": "USER_DIRECT"})` and a builder call with explicit `source_trust=USER_DIRECT` → assert `.source_trust == USER_DIRECT` and SAFE→ALLOW. Guards against the change accidentally downgrading legitimately-attested requests.

---

## 5. Risk of breaking existing examples / integrations

**Mechanism of risk:** flipping S3 (the dataclass default) changes every `ActionRequest(...)` that (a) omits `source_trust=` **and** (b) targets a **SAFE** action — those flip ALLOW→REQUIRE_APPROVAL. S1/S2 only affect wire input and are contained. S4 affects builder callers that omit trust on SAFE actions.

**What is NOT at risk (verified):**
- The **flagship exfil demo** sets `source_trust=TrustLevel.USER_DIRECT` explicitly ([`test_exfil_demo.py:103`](../../tests/test_exfil_demo.py)) — unaffected by any default flip.
- Tests/examples constructing **shell/write/critical/blocked** actions (the majority) — classification of those never used the absent-trust default; unaffected.
- The **adapter path** — already `UNKNOWN`; no change, so existing adapter tests hold.
- Tests that pass **explicit** `source_trust` (e.g. `test_universal_adapters.py` sends `"USER_DIRECT"`, `test_provenance.py`, `test_prompt_injection.py`) — explicit values are preserved.

**What IS at risk and must be swept before merge:**
- Any existing `ActionRequest(...)` for a **SAFE** action (`read_file`, `search_files`, `summarize`, `draft`, `analyze`) that omits `source_trust=` and asserts `ALLOW`. Required pre-work: grep `tests/` and `examples/` for SAFE-action constructions without explicit trust, then either (i) add `source_trust=TrustLevel.USER_DIRECT` where the test's intent is "trusted user," or (ii) update the expected decision to `REQUIRE_APPROVAL` where the intent is "unattested." This is mechanical, not a logic change.
- **External integrators** (PydanticAI / LangGraph / OpenAI-SDK examples, agent-runtimes plugin) that build SAFE requests without setting trust will see new approval prompts. This is the intended hardening, but it is a **behavior change for downstream users** and must be called out in `CHANGELOG.md` under a "Behavior change (security hardening)" heading.

**Scoping lever:** if you want this PR maximally small and zero-churn, ship **S1 + S2 only** (the two wire boundaries — the actual vulnerability) and **defer S3/S4** to a follow-up. S1+S2 close the live MCP and JSON-batch fail-opens with essentially no test churn (only the new T1–T4 file). S3/S4 are defense-in-depth against *future* callers and carry the example-breakage cost. Recommended: **S1+S2 required this PR; S3 strongly recommended; S4 optional with documented carve-out.**

---

## 6. Suggested PR shape

- **Title:** `security: fail closed to UNKNOWN trust when provenance is absent`
- **Commits:** (1) S1+S2 wire-boundary defaults + T1/T2/T3/T4 tests; (2) S3 dataclass default + sweep of SAFE-action test constructions; (3) optional S4 + carve-out note; (4) docs.
- **Labeled** in CHANGELOG as a security-hardening behavior change.
- **Explicitly states** in the description that forged `USER_DIRECT` remains an open, documented limitation (T3), addressed by a separate host-provenance effort — keeping this PR within the "small fail-closed hardening" boundary.
