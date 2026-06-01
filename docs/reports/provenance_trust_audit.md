# Provenance Trust Assumptions — Design Audit

**Type:** Design report. No code changes proposed.
**Question:** For every place Agent_Sudo consumes `source`, `provenance`, and `origin_type`, document (1) who supplies it, (2) whether it is trusted, (3) whether it is self-attested, (4) what happens if missing, (5) what happens if forged.
**Scope of code read:** `agent_sudo/adapters/common.py`, `agent_sudo/models.py`, `agent_sudo/mcp_validation.py`, `agent_sudo/classifier.py`, `agent_sudo/gateway.py`, `agent_sudo/builders.py`.

---

## TL;DR

Provenance is the load-bearing mechanism behind the product's headline claim ("the decision turns on *where the instruction came from*"). **Today, every provenance field is read verbatim from the inbound tool call and is never authenticated.** The caller — i.e. the agent, which is precisely the component we are trying to constrain — declares its own trust level.

Three structural problems:

1. **Self-attestation.** `source`, `origin_type`, `source_trust`, and the entire `provenance` object are taken directly from caller-supplied input. An explicit value always wins over inference.
2. **Fail-open asymmetry.** When provenance is *absent*, two of the three entry paths default to **`USER_DIRECT` (full trust)**. Missing provenance is treated as trusted, not untrusted.
3. **Dead authentication fields.** `provenance.authenticated` and `provenance.authentication_method` exist on the model and are serialized, but **no decision path ever reads them.** The one field that looks like it establishes trust does nothing.

Net: a compromised or prompt-injected agent bypasses provenance-based escalation by emitting `"source": "user"` (or `"source_trust": "USER_DIRECT"`, or `"origin_type": "USER_DIRECT"`) in its tool call. The flagship demo works only because the demo harness fills provenance in honestly.

---

## 1. Consumption sites (where these fields are read)

| # | Site | Code | Field(s) read | Effect |
|---|------|------|---------------|--------|
| C1 | MCP server input boundary | [`mcp_validation.py:60-61`](../../agent_sudo/mcp_validation.py) | `source`, `source_trust` from JSON-RPC message | Copies caller values into the tool-call dict; defaults `source="user"`, `source_trust="USER_DIRECT"` |
| C2 | Adapter normalizer | [`adapters/common.py:21-23`](../../agent_sudo/adapters/common.py) | `source`, `provenance`, `source_trust` | Builds `ActionRequest`; defaults `source="unknown"` |
| C3 | Origin inference | [`adapters/common.py:321-337`](../../agent_sudo/adapters/common.py) `_origin_type` | explicit `origin_type` else keyword-match on `source` | Explicit value wins; else infers from `source` substring |
| C4 | Trust inference | [`adapters/common.py:280-300`](../../agent_sudo/adapters/common.py) `_source_trust` | explicit `source_trust` else `origin_type` else `source` | Explicit value wins; else derives from origin/source |
| C5 | Provenance assembly | [`adapters/common.py:303-319`](../../agent_sudo/adapters/common.py) `_provenance` | whole `provenance` dict, or per-field defaults | If a `provenance` dict is present, it is used wholesale |
| C6 | Dict deserialization | [`models.py:130-160`](../../agent_sudo/models.py) `ActionRequest.from_dict` | `source`, `source_trust`, `provenance` | Alternate entry path (CLI/JSON); **fail-open default** (see §3) |
| C7 | Provenance deserialization | [`models.py:79-98`](../../agent_sudo/models.py) `Provenance.from_dict` | `origin_type`, `channel`, `authenticated`, … | Constructs `Provenance` from caller dict verbatim |
| C8 | **Decision: classifier escalation** | [`classifier.py:103-108`](../../agent_sudo/classifier.py) | `provenance.origin_type`, `source_trust` | `EXTERNAL_CONTENT`/`UNKNOWN` → escalate SAFE→SENSITIVE. **Only place provenance changes a verdict.** |
| C9 | **Decision: gateway handling** | [`gateway.py:410-411`](../../agent_sudo/gateway.py) | `source_trust`, `provenance.origin_type` | `EXTERNAL_CONTENT` branch in evaluation |
| C10 | Builders (in-process API) | [`builders.py:18-230`](../../agent_sudo/builders.py) | caller passes `source`/`source_trust`/`provenance` | Defaults to `source="user"`, `source_trust=USER_DIRECT` |

**Crucial observation about C8/C9:** provenance only ever *raises* scrutiny when the caller volunteers a low-trust signal. There is no path where a high-trust declaration is challenged. Escalation is opt-in by the caller's own honesty.

---

## 2. Per-field analysis (the five questions)

### `source` (free-form string)

1. **Who supplies it:** the inbound tool call / JSON-RPC message — i.e. the agent or client runtime. ([`common.py:21`](../../agent_sudo/adapters/common.py), [`mcp_validation.py:60`](../../agent_sudo/mcp_validation.py))
2. **Trusted?** Yes, implicitly — it seeds both `origin_type` and `source_trust` inference via keyword matching.
3. **Self-attested?** **Yes.** Pure caller assertion, no verification.
4. **If missing:** `common.py` → `"unknown"` → `OriginType.UNKNOWN` → `TrustLevel.UNKNOWN` (fails toward *more* scrutiny — SENSITIVE). `mcp_validation.py` and `builders.py` → `"user"` (fails toward *full trust*). **Inconsistent.**
5. **If forged:** `"source": "user"` ⇒ `USER_DIRECT` origin and trust ([`common.py:325-327`](../../agent_sudo/adapters/common.py)). The untrusted-origin escalation at C8 never fires. Full bypass of the headline mechanism.

### `origin_type` (enum)

1. **Who supplies it:** caller, via `tool_call["origin_type"]` or inside a `provenance` dict.
2. **Trusted?** Yes — directly drives C8 escalation and `_trust_from_provenance`.
3. **Self-attested?** **Yes.** Explicit value is accepted verbatim and takes precedence over `source`-based inference ([`common.py:322-324`](../../agent_sudo/adapters/common.py)).
4. **If missing:** inferred from `source`; if that is also absent → `UNKNOWN` (escalates).
5. **If forged:** `"origin_type": "USER_DIRECT"` ⇒ no escalation regardless of the real source. A poisoned-webpage action labeled `USER_DIRECT` is treated as the operator's own.

### `source_trust` (enum)

1. **Who supplies it:** caller, via `tool_call["source_trust"]`; or derived from `origin_type`; or from `source`.
2. **Trusted?** Yes — read at C8 ([`classifier.py:107`](../../agent_sudo/classifier.py)) and C9 ([`gateway.py:410`](../../agent_sudo/gateway.py)).
3. **Self-attested?** **Yes,** and it is the *highest-precedence* override: an explicit `source_trust` short-circuits all inference ([`common.py:283-285`](../../agent_sudo/adapters/common.py), [`models.py:142-143`](../../agent_sudo/models.py)).
4. **If missing:** derived; final fallback differs by path — `UNKNOWN` in `common.py`, **`USER_DIRECT` in `models.py` / `mcp_validation.py`**.
5. **If forged:** `"source_trust": "USER_DIRECT"` ⇒ trust-based escalation disabled. Note there is **no cross-field consistency check** — `source="webpage"` + `source_trust="USER_DIRECT"` is accepted as-is.

### `provenance` (object: origin_type, channel, authenticated, authentication_method, session_id, request_id, parent_request_id, delegation_chain)

1. **Who supplies it:** caller; an inbound `provenance` dict is consumed wholesale ([`common.py:304-306`](../../agent_sudo/adapters/common.py)).
2. **Trusted?** `origin_type` is trusted (C8). The rest is stored/logged but mostly inert.
3. **Self-attested?** **Yes,** entirely. Including `authenticated` / `authentication_method` and `delegation_chain`.
4. **If missing:** `Provenance()` default → `origin_type=UNKNOWN`, `authenticated=False`. (Escalates at C8 via UNKNOWN trust — but see the `from_dict` fail-open in §3.)
5. **If forged:** any field can be set. `authenticated: true` is accepted but, critically, **also irrelevant** — no code reads it (§4). `delegation_chain` is unvalidated free text.

---

## 3. The fail-open asymmetry (highest-severity finding)

Two entry paths disagree on what "no provenance" means:

| Entry path | Missing `source_trust` AND missing `provenance` → |
|---|---|
| [`adapters/common.py`](../../agent_sudo/adapters/common.py) (MCP/native tool calls) | `source="unknown"` → `TrustLevel.UNKNOWN` → **escalates** (fail-safe) |
| [`models.py:142-147` `ActionRequest.from_dict`](../../agent_sudo/models.py) (CLI/JSON requests) | **`TrustLevel.USER_DIRECT`** (fail-open) |
| [`mcp_validation.py:60-61`](../../agent_sudo/mcp_validation.py) | defaults `source_trust="USER_DIRECT"` (fail-open) |
| `ActionRequest` dataclass default ([`models.py:126`](../../agent_sudo/models.py)) | `source_trust = TrustLevel.USER_DIRECT` (fail-open) |

The dataclass *default* for trust is full trust. So any code path or future caller that constructs an `ActionRequest` without explicitly setting provenance gets `USER_DIRECT` for free. **The safe default (`UNKNOWN`) is the exception, not the rule.** For a security boundary, the default must invert: absence of trustworthy provenance should mean *least* trust, not most.

---

## 4. Dead authentication fields

`Provenance.authenticated` (bool) and `Provenance.authentication_method` (enum) are:
- **Written** from caller input ([`common.py:310-312`](../../agent_sudo/adapters/common.py), [`models.py:88-96`](../../agent_sudo/models.py)).
- **Serialized** into audit logs ([`models.py:108-109`](../../agent_sudo/models.py)).
- **Never read** by any classifier or gateway decision. A grep for reads of `.authenticated` returns only `to_dict`/`from_dict` serialization.

So the model *has the vocabulary* to express "this origin was cryptographically authenticated," but nothing acts on it. This is the natural hook for a fix (see §6) and currently a no-op that can mislead a reader of the schema into thinking authentication is enforced.

---

## 5. Representative forge scenarios

| Scenario | Crafted tool call | Result | Why |
|---|---|---|---|
| Trust spoof via `source` | `{"source": "user", "action": "run_shell_command", …}` | Treated as `USER_DIRECT`; no provenance escalation | C3 keyword match |
| Trust spoof via explicit trust | `{"source": "webpage", "source_trust": "USER_DIRECT", …}` | `USER_DIRECT` wins; **inconsistent with source, not flagged** | C4 precedence, no cross-check |
| Origin spoof | `{"origin_type": "USER_DIRECT", …}` | C8 escalation skipped | C3 explicit branch |
| Fake authentication | `{"provenance": {"authenticated": true, "authentication_method": "signature"}}` | Logged as authenticated; **changes nothing** (also not verified) | §4 dead field |
| Fake delegation chain | `{"provenance": {"delegation_chain": ["operator","ci"]}}` | Stored/logged as provenance lineage | unvalidated free text |

In all cases the *only* real backstop that still fires is target-based blocking (protected paths, blocked shell targets) and `risk_hints` — none of which depend on provenance. Those remain effective; the provenance layer specifically does not.

---

## 6. Design recommendations (no code in this report)

Ordered by leverage. All are design positions for discussion, not implementations.

1. **Invert the default to fail-closed.** Absent/unparseable provenance → `UNKNOWN` (or a new `UNTRUSTED`) everywhere, including the `ActionRequest` dataclass default and `from_dict`. Unify the three entry paths on one default. This alone removes the worst footgun.

2. **Separate caller-asserted from host-stamped provenance.** Treat `source`/`origin_type`/`source_trust` arriving in a tool call as *claims*, not facts. The trustworthy value must be stamped by the **host/runtime** (the component that actually knows which conversation turn or which fetched document produced the call), recorded in a field the agent cannot write. Document explicitly: "provenance is only as trustworthy as the host that stamps it; agent-supplied provenance is advisory."

3. **Make `authenticated` load-bearing — or remove it.** Either (a) gate elevated trust on `authenticated == true` *and* a verified `authentication_method` (e.g. a host-issued signature/nonce the agent can't mint), so that `USER_DIRECT` requires proof; or (b) delete the fields so the schema does not imply a guarantee that isn't enforced. Option (a) is the real fix; (b) is the honest stopgap.

4. **Add cross-field consistency checks.** Reject or down-rank requests where `source` and `source_trust`/`origin_type` disagree (e.g. `source="webpage"` + `USER_DIRECT`). Inconsistency is a strong tamper signal and should escalate, not be silently honored via precedence.

5. **Bind elevation to a host-issued token/nonce.** To claim `USER_DIRECT`, require a per-session secret the gateway issued to the trusted host out-of-band — not something the agent can guess or replay. This is the mechanism that makes #2 enforceable rather than documentary. (Already foreshadowed as "Approval Nonce Binding" / "Signed Delegation Tokens" in [`security_model.md` §6](../../docs/architecture/security_model.md).)

6. **Validate `delegation_chain`.** It currently accepts arbitrary strings into the audit record. At minimum, mark it as untrusted-when-agent-supplied; ideally tie entries to issued delegation tokens.

### Honest framing in the meantime

Until #2/#3/#5 land, the docs should state plainly (consistent with the recent messaging pass): **provenance-based escalation protects against an *honest-but-confused* agent that correctly labels untrusted input, not against a *compromised* agent that lies about origin.** That is still a real and useful threat model — it's the difference between "the agent got tricked by a web page and told us so" and "the agent is actively adversarial" — but the boundary should be named, not implied away.

---

## Appendix: trust-decision call graph

```
inbound tool_call / JSON-RPC  (agent-supplied)
        │
        ├─ mcp_validation.tool_call_from_jsonrpc   source/​source_trust default → USER_DIRECT   [C1, fail-open]
        │
        ├─ adapters.common.normalize_tool_call
        │     ├─ _origin_type   explicit > source-keyword > UNKNOWN          [C3, self-attested]
        │     ├─ _source_trust  explicit > origin_type > source > UNKNOWN    [C4, self-attested]
        │     └─ _provenance    whole dict accepted verbatim                 [C5, self-attested]
        │
        └─ models.ActionRequest.from_dict   missing trust → USER_DIRECT      [C6, fail-open]
                        │
                        ▼
        classifier.classify
            ├─ origin_type == EXTERNAL_CONTENT → SENSITIVE                   [C8]  ◄─ only escalation points
            └─ source_trust ∈ {EXTERNAL_CONTENT, UNKNOWN} → SENSITIVE        [C8]
                        │
                        ▼
        gateway.evaluate   EXTERNAL_CONTENT branch                          [C9]

   provenance.authenticated / authentication_method ─────────────► (never read)   [§4]
```
