# Messaging Accuracy Audit — Docs-Only

**Scope:** All README and documentation language (no website assets exist in-repo; "website" = README + `docs/` + `spec/` + example READMEs).
**Goal:** Find language that claims (A) prompt-injection *prevention*, (B) *complete* tool-execution control, or (C) stronger enforcement than the code provides — and recommend wording that re-centers the real strengths (policy, audit, delegation, provenance).
**Constraint:** Documentation changes only. No code changes proposed.

---

## Executive summary

Agent_Sudo's docs are, on the whole, unusually honest — the README has a dedicated **Trust Boundaries** table and **Security Boundaries Notice**, and several internal docs (`release_checklist.md`, `review_response.md`, `release_report_v0_1_0.md`, the `exfil_demo` body) explicitly downgrade the injection detector to "primitive / not protection by itself." The accurate framing already exists in the repo.

The problem is **isolated to headlines and high-visibility one-liners**, where the careful body text is undercut by a stronger title. The single recurring error: **attributing the flagship demo's win to "prompt-injection" defense when the actual enforcement mechanism is provenance-based escalation.** The regex phrase-detector ([`agent_sudo/injection.py`](../../agent_sudo/injection.py), 9 patterns) is a separate, weak component that does *not* do the blocking shown in the demo.

**The mechanism truth, stated once:** In the flagship demo, the exfiltration is denied because `provenance.origin_type == EXTERNAL_CONTENT` escalates/blocks the action — *regardless of wording*. That is a real, strong capability. The phrase detector is a best-effort tripwire that fires on a handful of literal strings. Conflating the two oversells the weak part and undersells the strong part.

---

## A. Claims of prompt-injection *prevention*

| # | Location | Current text | Issue | Recommended wording |
|---|---|---|---|---|
| A1 | [README.md:192](../../README.md) | `### Flagship Demo: Stop Prompt-Injection Exfiltration` | Headline says the product *stops prompt injection*. The body correctly credits **provenance** ("untrusted origin"), but the title names the mechanism wrongly. | `### Flagship Demo: Block Exfiltration by Provenance` — and in the blurb, lead with: "An agent reads a poisoned web page; because the instruction's **origin is untrusted external content**, Agent_Sudo escalates/denies it — independent of the wording used." |
| A2 | [examples/exfil_demo/README.md:1](../../examples/exfil_demo/README.md) | `# 60-Second Demo: Stop Prompt-Injection Exfiltration` | Same title issue. (The body of this file is **exemplary** — it already says "the action's provenance is untrusted external content, not you" and "it is not tamper-proof.") | `# 60-Second Demo: Block Exfiltration by Provenance`. Keep the body verbatim — it is the model the rest of the docs should follow. |
| A3 | [docs/architecture/security_model.md:21](../../docs/architecture/security_model.md) | "**Prompt Injection Risks**: Intercepts actions triggered by injected content … and **blocking obvious override keyword patterns**." | "Intercepts actions triggered by injected content" implies reliable interception of injection; "blocking obvious override keyword patterns" presents the regex tripwire as an enforcement layer. | "**Injected-instruction risk (partial)**: Treats actions whose provenance is untrusted/external content as higher-risk and escalates them to human approval. A best-effort phrase detector additionally flags a small set of literal override strings — this is a **signal/tripwire, not a content-security boundary**, and is trivially bypassed by paraphrase." |
| A4 | [docs/releases/release_notes_v0_4_0.md:11,14](../../docs/releases/release_notes_v0_4_0.md) | Section header `### 1. Robust Security Boundaries & Injection Gating`; bullet "**Prompt-Injection Defense**: Built-in phrase-based detector…" | "Injection Gating" / "Defense" frame a phrase detector as a defense layer. The bullet body ("flags obvious injection patterns") is accurate. | Rename header to `### 1. Security Boundaries & Provenance Gating`. Rename bullet to "**Injection tripwire (best-effort)**: phrase-based detector that flags a few obvious literal injection patterns as a signal — not a defense against prompt injection." |
| A5 | [docs/reports/release_readiness_report_v0_3_4.md:49](../../docs/reports/release_readiness_report_v0_3_4.md) | "A **semantic firewall that prevents prompt injections**, excessive agency, and unapproved tool execution." | Strongest single overclaim in the repo. "Semantic firewall that prevents prompt injections" asserts prevention the system does not deliver. | "A policy-and-provenance gateway that **reduces excessive agency and unapproved tool execution** by requiring human approval for sensitive/critical actions and escalating untrusted-origin actions. It does **not** prevent prompt injection." |
| A6 | [docs/ecosystem/discoverability_notes.md:48](../../docs/ecosystem/discoverability_notes.md) | Outreach guidance: "showcasing how to **protect Claude Desktop from prompt injection** using Agent_Sudo's local rules engine." | Directs contributors to publish the inaccurate framing externally — it propagates the overclaim into blog posts. | "…showcasing how Agent_Sudo **limits the blast radius of prompt-injected agents** by gating untrusted-origin tool calls and requiring approval — not by detecting injection in prose." |

**Already-correct anchors to preserve and emulate** (no change): `docs/releases/release_checklist.md:26` ("primitive phrase detector, not a full content-security system"), `docs/reports/review_response.md:77` ("should not be treated as prompt-injection protection by itself"), `docs/reports/release_report_v0_1_0.md:92` ("intentionally primitive"), and the `exfil_demo/README.md` body.

---

## B. Claims of *complete* tool-execution control

| # | Location | Current text | Issue | Recommended wording |
|---|---|---|---|---|
| B1 | [README.md:14](../../README.md) | "a local permission gateway for AI agents that validates, authorizes, and **controls tool execution** before actions are run." | This is the most-quoted line (mirrored in the PyPI/`pyproject.toml` description). Unqualified "controls tool execution" reads as comprehensive control; the Trust Boundaries section 170 lines later says it only sees calls *routed through it*. The qualifier should ride with the claim. | "a local permission gateway for AI agents that validates, authorizes, and gates **the tool calls routed through it** — classifying, approving, and logging each one before it runs." |
| B2 | [docs/reports/release_readiness_report_v0_3_4.md:49](../../docs/reports/release_readiness_report_v0_3_4.md) | "…and **unapproved tool execution**." (same sentence as A5) | Implies it prevents *all* unapproved execution; native/other-MCP tools bypass it. | Covered by the A5 rewrite ("reduces… unapproved tool execution") plus a clause: "…for tool calls routed through the gateway; tools not routed through it are neither gated nor audited." |

**Already-correct anchors** (no change): README "Security Boundaries Notice" (Client Runtime Bypass), README "Trust Boundaries: What Is and Is Not Protected" table, `security_model.md` §1 and §2 "Does NOT Protect Against." These are model statements; the fix for B is to make the *opening* lines consistent with them.

---

## C. Stronger enforcement than the code provides

| # | Location | Current text | Issue | Recommended wording |
|---|---|---|---|---|
| C1 | [docs/releases/release_notes_v0_4_0.md:11](../../docs/releases/release_notes_v0_4_0.md) | "**Shell Command Deep-Scanning**: Implements recursive substring and argument scans to **detect and block** directory traversals … subshell escapes … utility abuse." | The README's own Security Boundaries Notice calls shell filtering **"best-effort unless reinforced by OS-level containment."** The release-note bullet presents it as robust detect-and-block with no caveat — a mismatch between two docs. | "**Shell command screening (best-effort)**: substring/argument scans that flag common bypass shapes (`../`, `$VAR` expansion, `bash -c`, `mv`/`cp`/`ln`/`tar`/`tee`/`dd`/`cat`). This is **pattern-based and best-effort** — not a complete shell parser; pair with OS-level containment for a real boundary." |
| C2 | [docs/architecture/security_model.md:18-22](../../docs/architecture/security_model.md) | §2 "**What Agent_Sudo Protects Against**" lists "Prompt Injection Risks" as a peer of genuinely-enforced items (excessive agency, log tampering). | Listing the weak tripwire alongside enforced protections elevates it by association. | Move injection out of the enforced list (apply A3 wording), or split the section into "**Enforced**" (approval gates, provenance escalation, protected paths, hash-chain audit) vs "**Best-effort signals**" (phrase detector, shell screening). |

---

## Cross-cutting recommendation: one "What this is / isn't" capsule

The repo says the honest thing in ~6 places and the overclaiming thing in ~6 headlines. Reduce drift with a single canonical capsule, defined once (suggest top of `security_model.md`) and linked from README, release notes, and demo READMEs:

> **What Agent_Sudo is:** a policy + provenance gateway with human approval gates, scoped delegation, and a tamper-**evident** (hash-chained) audit log, for the tool calls routed through it.
> **What it is not:** a sandbox, a prompt-injection detector, or a guarantee over tools that bypass it. Injection phrase-matching and shell screening are **best-effort signals**, not boundaries.

Lead every surface with the four real strengths — **policy classification, human-in-the-loop approval, scoped delegation, tamper-evident audit** — and frame injection handling as **provenance-based escalation + a tripwire signal**. That is both more accurate and a stronger pitch, because provenance-based blocking is the genuinely differentiated capability the weak-injection framing currently hides.

---

## Change inventory (docs-only, for tracking)

| File | Lines | Category | Action |
|---|---|---|---|
| `README.md` | 14 | B | Reword tagline → "gates the tool calls routed through it" |
| `README.md` | 192 + blurb | A | Retitle flagship demo to provenance; lead blurb with mechanism |
| `examples/exfil_demo/README.md` | 1 | A | Retitle only; keep body |
| `docs/architecture/security_model.md` | 21 | A | Rewrite injection bullet as signal/tripwire |
| `docs/architecture/security_model.md` | 18–22 | C | Split Enforced vs Best-effort signals |
| `docs/releases/release_notes_v0_4_0.md` | 11 | C | Add "best-effort" to shell screening |
| `docs/releases/release_notes_v0_4_0.md` | 14 + header 1 | A | "Defense/Gating" → "tripwire (best-effort)" |
| `docs/reports/release_readiness_report_v0_3_4.md` | 49 | A,B | Drop "semantic firewall that prevents prompt injections" |
| `docs/ecosystem/discoverability_notes.md` | 48 | A | Reframe outreach guidance away from "protect from prompt injection" |
| `security_model.md` (new capsule) | top | cross | Add canonical "is / isn't" capsule, link from README + release notes + demos |

No code changes recommended. The code's behavior (provenance escalation, approval gates, hash-chain audit, best-effort shell/phrase screening) is accurately representable with the wording above; the gap is purely in how a few headlines describe it.
