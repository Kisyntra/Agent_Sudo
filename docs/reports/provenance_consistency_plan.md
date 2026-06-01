# Implementation Plan — Cross-Field Provenance Consistency Checks

**Type:** Plan only. No code in this document.
**Goal:** Detect *contradictory* provenance claims and fail closed — never silently honor a higher `source_trust` than the accompanying `source` / `origin_type` evidence supports. Downgrade to the most restrictive level the evidence justifies (`EXTERNAL_CONTENT` or `UNKNOWN`) and record an explaining reason.

**Builds on:** [#28 fail-closed defaults](fail_closed_provenance_plan.md). This PR addresses the *next* layer: #28 handles *absent* provenance; this handles *internally inconsistent* provenance.

**Out of scope (constraints):** signatures, nonce binding, host attestation, architecture redesign. A *consistent* forgery (e.g. `source="user"` + `origin_type=USER_DIRECT` + `source_trust=USER_DIRECT` from a compromised agent) remains a documented known limitation — it is internally consistent, so this check cannot catch it.

---

## 1. Root cause

Explicit `source_trust` is accepted verbatim at two sites, with no cross-check against the other provenance fields:

- [`adapters/common.py:283-285`](../../agent_sudo/adapters/common.py) `_source_trust` — `if isinstance(raw, str): return TrustLevel(raw)`
- [`models.py:142-143`](../../agent_sudo/models.py) `ActionRequest.from_dict` — `if "source_trust" in data: source_trust = TrustLevel(str(data["source_trust"]))`

So `source="webpage"` + `source_trust="USER_DIRECT"` is honored as USER_DIRECT at the field level. (The classifier sometimes catches the downstream effect via its `origin_type == EXTERNAL_CONTENT` branch, but the *trust field itself* stays a lie — it lands in the audit log and is read by other consumers such as [`gateway.py:410`](../../agent_sudo/gateway.py) and delegation. The fix makes the field honest at resolution time and produces an explicit reason.)

---

## 2. Exact downgrade rule

A single pure helper, `reconcile_trust(claimed, source, origin_type) -> (resolved, reason | None)`, applied **only when `source_trust` is explicitly provided** (so #28's absent-provenance path is untouched).

Trust rank (higher = more trusted): `USER_DIRECT=3 > AGENT_INTERNAL=2 > EXTERNAL_CONTENT=1 > UNKNOWN=0`.

```
evidence = []                              # trust levels that opinionated signals imply
# origin_type opinion
if origin_type in {EXTERNAL_CONTENT, EXTERNAL_API}: evidence += [EXTERNAL_CONTENT]
elif origin_type == AGENT_INTERNAL:                 evidence += [AGENT_INTERNAL]
elif origin_type == USER_DIRECT:                    evidence += [USER_DIRECT]
# (origin_type UNKNOWN / LOCAL_UI: no opinion — left to the #28 regime)
# source opinion (same token sets the adapter already uses)
s = source.lower()
if s in {"user","human","user_direct"}:                              evidence += [USER_DIRECT]
elif any(tok in s for tok in EXTERNAL_TOKENS):                        evidence += [EXTERNAL_CONTENT]
#   EXTERNAL_TOKENS = {web, email, document, external, slack, browser}

if not evidence:                 # nothing has an opinion -> honor claim (#28 limitation regime)
    return claimed, None
ceiling = min(evidence, by rank) # most restrictive opinion present
if rank(claimed) > rank(ceiling):
    return ceiling, (
        f"inconsistent provenance: source_trust={claimed.value} exceeds "
        f"evidence (source={source!r}, origin_type={origin_type.value}); "
        f"downgraded to {ceiling.value}"
    )
return claimed, None             # claim within evidence, or caller self-restricting -> honor
```

**Key properties:**
- **Downgrade only, never upgrade.** Only `rank(claimed) > rank(ceiling)` triggers a change. A caller may always self-restrict (claim *lower* than evidence).
- **Floor across signals.** If `source` and `origin_type` disagree with each other (e.g. `source="user"` but `origin_type=EXTERNAL_CONTENT`), the *more restrictive* wins.
- **Neutral signals don't contradict.** `origin_type=UNKNOWN` / unknown source contribute no opinion, so they neither trigger a downgrade nor disturb #28.

---

## 3. Behavior — before / after

| Input (explicit `source_trust`) | Before | After |
|---|---|---|
| `source="webpage"`, `source_trust="USER_DIRECT"` (origin inferred EXTERNAL_CONTENT) | trust field = USER_DIRECT (lie recorded); SAFE→SENSITIVE only incidentally via origin branch | trust = **EXTERNAL_CONTENT**; SAFE→SENSITIVE→**REQUIRE_APPROVAL**; reason names the inconsistency |
| `origin_type="EXTERNAL_CONTENT"`, `source="user"`, `source_trust="USER_DIRECT"` | trust field = USER_DIRECT | trust = **EXTERNAL_CONTENT**; **REQUIRE_APPROVAL** + reason |
| `source="slack"`, `source_trust="USER_DIRECT"` | USER_DIRECT honored | trust = **EXTERNAL_CONTENT**; **REQUIRE_APPROVAL** + reason |
| `source="user"`, `origin_type="USER_DIRECT"`, `source_trust="USER_DIRECT"` (consistent) | ALLOW | **ALLOW** (unchanged — consistent claim honored) |
| `source="user"`, `source_trust="USER_DIRECT"`, no provenance (consistent) | ALLOW | **ALLOW** (unchanged) |
| no `source_trust` at all (#28) | UNKNOWN | **UNKNOWN** (unchanged — reconcile not invoked) |
| `source_trust="UNKNOWN"` with `source="user"` (self-restrict) | UNKNOWN | **UNKNOWN** (unchanged — downgrade-only) |

**Net classifier effect:** the downgrade to `EXTERNAL_CONTENT` drives escalation through the *existing* `source_trust in {EXTERNAL_CONTENT, UNKNOWN}` branch ([`classifier.py:107`](../../agent_sudo/classifier.py)) — **no classifier change required.** Non-SAFE actions are already ≥SENSITIVE, so they are unaffected in outcome but still get the honest trust field + reason.

---

## 4. Affected files

**Code (3):**
- `agent_sudo/models.py` — add `reconcile_trust()` (+ a small `_trust_rank` helper next to the existing `_trust_from_provenance`); call it in `from_dict` when `source_trust` is explicit; append an `inconsistent_provenance: …` risk hint when a downgrade occurs.
- `agent_sudo/adapters/common.py` — in `normalize_tool_call`, after computing `source_trust` and `provenance`, call `reconcile_trust(source_trust, source, provenance.origin_type)`; on downgrade, replace `source_trust` and append the hint to `risk_hints`. (Imports `reconcile_trust` from `models` — common.py already depends on models, no cycle.)
- `agent_sudo/gateway.py` — in `evaluate`, after `reason = policy_result.reason`, if any risk hint starts with `inconsistent_provenance`, append it to `reason` (~3 lines). Surfaces the explanation in the decision + audit record.

**No change** to `classifier.py` (escalation rides the trust downgrade), `executors.py`, target/path blocking, or the `ActionRequest`/`Provenance` schema.

**Docs (2):** `docs/architecture/security_model.md` (extend the "Default Trust Posture" section with a contradiction paragraph) and `CHANGELOG.md` (Unreleased note).

**Tests (1 new file):** `tests/test_provenance_consistency.py`.

---

## 5. Test plan (`tests/test_provenance_consistency.py`)

1. **Contradictory `source`/`source_trust` requires approval.** `from_mcp_tool_call({source:"webpage", source_trust:"USER_DIRECT", read_file})` → `request.source_trust == EXTERNAL_CONTENT`; gateway (dry-run) → `REQUIRE_APPROVAL`; an `inconsistent_provenance` hint is present and the decision `reason` mentions it.
2. **Contradictory `origin_type`/`source_trust` requires approval.** `from_mcp_tool_call({source:"user", origin_type:"EXTERNAL_CONTENT", source_trust:"USER_DIRECT", read_file})` → downgraded to `EXTERNAL_CONTENT` → `REQUIRE_APPROVAL` + reason.
3. **Model path parity.** Same two contradictions via `ActionRequest.from_dict(...)` → identical `EXTERNAL_CONTENT` + hint (guards adapter/model drift, mirroring #28's parity test).
4. **Consistent USER_DIRECT still allows SAFE actions.** `source="user"`, `origin_type="USER_DIRECT"`, `source_trust="USER_DIRECT"`, `read_file` → `ALLOW`; no `inconsistent_provenance` hint.
5. **Self-restriction honored.** `source="user"`, `source_trust="UNKNOWN"` → stays `UNKNOWN` (no upgrade, no false "inconsistency").
6. **#28 invariants unchanged.** Missing `source_trust` (no provenance) → `UNKNOWN` and `REQUIRE_APPROVAL` for SAFE; explicit consistent `USER_DIRECT` → `ALLOW`. (Re-assert here so this PR can't silently regress #28.)
7. **Forged-but-consistent USER_DIRECT remains a known limitation.** `source="user"`, `origin_type="USER_DIRECT"`, `source_trust="USER_DIRECT"` → still `ALLOW`. Named/docstring'd as intentionally out of scope (needs host attestation), pinning the boundary — same spirit as #28's `test_forged_user_direct_is_still_trusted_known_limitation`.

**Regression sweep:** none expected. The existing #28 attestation tests use `source="user"` + `source_trust="USER_DIRECT"` (consistent) → no downgrade. Verify the full suite + ruff before opening.

---

## 6. Release note wording (CHANGELOG, Unreleased)

> - **Security hardening: contradictory provenance is reconciled, not trusted.** When a request asserts a `source_trust` higher than its `source` / `origin_type` evidence supports (e.g. `source="webpage"` or `origin_type="EXTERNAL_CONTENT"` paired with `source_trust="USER_DIRECT"`), the gateway now downgrades the trust to the most restrictive level the evidence supports (`EXTERNAL_CONTENT`/`UNKNOWN`) instead of honoring the inflated claim, and records an `inconsistent_provenance` reason on the decision and audit entry. **Impact:** such requests are escalated to `REQUIRE_APPROVAL` rather than allowed. Internally *consistent* provenance — including an explicit `USER_DIRECT` whose `source`/`origin_type` agree — is honored exactly as before. A consistently-forged `USER_DIRECT` remains a known limitation pending host attestation. See [`docs/architecture/security_model.md`](docs/architecture/security_model.md) (Default Trust Posture).

---

## 7. PR shape

- **Title:** `security: reconcile contradictory provenance claims instead of trusting them`
- **Commits:** (1) `reconcile_trust` + wiring in both entry paths + gateway reason; (2) tests; (3) docs/CHANGELOG.
- **Size:** ~1 helper + 2 call sites + 3-line gateway reason + 1 test file + docs. Comparable to #28.
- Explicitly states the consistent-forgery limitation and that no signatures / nonce binding / host attestation are introduced.
