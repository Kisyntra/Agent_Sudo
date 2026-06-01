# Design Report — Bypass-Verification Doctor Check

**Type:** Design only. No implementation in this document.
**Goal:** Help a user determine whether their agent's actions are actually flowing **through** Agent_Sudo — and, critically, be honest about the large part of that question that cannot be answered from local state.

**Hard constraint (non-negotiable):** the command must never assert *"you are protected."* Agent_Sudo cannot prove that. It can only report observed signals and name what it cannot see. Every line is scoped to a verb it can stand behind: *observed*, *verified*, *configured*, *cannot be proven*.

---

## 1. The questions, answered

### What can be observed reliably?
All of these are read from local state Agent_Sudo owns or can parse:

| Signal | Source | Strength |
|---|---|---|
| Approvals initialized | `~/.agent-sudo/config.json` ([approvals.py](../../agent_sudo/approvals.py)) | **fact** |
| Workspace configured | `~/.agent-sudo/config.json` ([context.py](../../agent_sudo/context.py)) | **fact** |
| Default policy loadable | `agent_sudo/config/default_policy.yaml` | **fact** |
| Audit log exists | `~/.agent-sudo/mcp-audit.jsonl` / workspace `.agent-sudo/` | **fact** |
| Requests reached the gateway | audit record count + last timestamp ([audit.read_audit_entries](../../agent_sudo/audit.py)) | **fact (past tense)** |
| How those requests were decided | decision histogram (ALLOW / REQUIRE_APPROVAL / DENY) | **fact (past tense)** |
| Audit log integrity | hash-chain verify ([audit.verify_audit_log](../../agent_sudo/audit.py)) | **cryptographic fact** |
| agent-sudo registered in a client config | best-effort parse of known client config files | **fact, if the file is readable** |
| Other MCP servers present in that config | same parse | **fact, if readable — but see below** |

### What can be *verified* (proven), vs merely observed?
- **Cryptographically verified:** audit-log integrity (the hash chain). If it verifies, the recorded decisions have not been altered after the fact.
- **Verified by presence:** config initialized, agent-sudo listed in a client config, an audit log with N records exists.
- **Observed but not proof of a property:** "requests reached the gateway" proves *some* traffic is routed — it does **not** prove *all* risky traffic is routed.

### What cannot be verified (the honest limits)?
1. **Routing completeness.** Agent_Sudo only sees what is sent to it. It cannot prove that a given dangerous capability *isn't* also reachable by an unrouted path. You cannot prove a negative from inside the gateway.
2. **Client native tools.** Claude Desktop's (or any client's) built-in file/web tools don't appear in `mcpServers` and are invisible to us. We can't enumerate them.
3. **What other MCP servers actually expose.** We can see another server is *named* in the config; we cannot know whether it exposes filesystem/shell/network. Name/command are heuristics, not capability proofs.
4. **Real-time / future protection.** The audit log is past tense. "Verified at 14:02" says nothing about the next tool call.
5. **The meaning of silence.** Zero recent records is ambiguous: the agent may simply not have acted, *or* it may be acting through a path Agent_Sudo never sees. Absence of records is **not** evidence of safety.

### How should results be presented?
Grouped by epistemic status, never aggregated into a single verdict. Three positive section headers scoped to what each proves, plus a standing "trust boundary" section of `⚠` limitations that **always prints regardless of how healthy the setup looks**. Icon vocabulary:
- `✓` an observed fact (past tense, provable from local state)
- `⚠` an inherent limitation, or a best-effort signal we can't fully stand behind
- `✗` a misconfiguration we *can* prove (e.g. approvals not initialized)

### How do we avoid claiming protection we can't prove?
- **No aggregate "protected" line. No overall PASS.** The command has no single green verdict to give.
- Section headers carry the scope: *"what actually reached the gateway"*, not *"you are safe."*
- The `⚠` trust-boundary block prints **every run**, including a fully-configured one — the limitation is structural, not a setup defect.
- Silence is framed as ambiguous, never as safety.
- A closing disclaimer states plainly: *this reports observed signals; it cannot certify protection.*

---

## 2. Proposed command + output

**Command:** a dedicated subcommand, `agent-sudo verify-routing` (keeps the readiness-focused `doctor` and its exit-code contract separate from this evidence report; `doctor` can print a one-line pointer to it). *Alternative considered:* a `doctor --routing` flag — rejected to avoid mixing "is my install OK" (gating exit code) with "is traffic flowing through me" (informational).

```
$ agent-sudo verify-routing

Configuration (what is set up)
  ✓ approvals initialized         ~/.agent-sudo/config.json
  ✓ workspace configured          /Users/you/project
  ✓ default policy loaded         agent_sudo/config/default_policy.yaml

Observed gateway activity (what actually reached the gateway — past tense)
  ✓ audit log present             ~/.agent-sudo/mcp-audit.jsonl
  ✓ audit integrity verified      142 records, hash chain intact
  ✓ requests observed             last decision 3m ago
                                   ALLOW 110 · REQUIRE_APPROVAL 30 · DENY 2

MCP client wiring (best-effort — parsed from client config if present)
  ✓ agent-sudo registered         Claude Desktop config
  ⚠ 2 other MCP servers present   'filesystem', 'shell-runner' — these may
                                   expose tools that bypass agent-sudo

Trust boundary (cannot be proven from local state)
  ⚠ Native/built-in client tools execute outside agent-sudo and are invisible here
  ⚠ Only tool calls routed through agent-sudo are gated and audited
  ⚠ No recent records is NOT proof of safety — the agent may not have acted,
    or may be acting through an unrouted path

This command reports observed signals. It cannot certify that you are protected.
To confirm a specific action was gated, perform it, then run `agent-sudo audit list`.
```

**The "nothing yet" state** (configured but no traffic):
```
Observed gateway activity (what actually reached the gateway — past tense)
  ✓ audit log present             ~/.agent-sudo/mcp-audit.jsonl
  ⚠ no requests observed yet      run a tool through your agent, then re-check
```
This is a `⚠`, not a `✗` — an empty log is a normal pre-use state, not a failure.

**A provable misconfiguration:**
```
Configuration (what is set up)
  ✗ approvals not initialized     run: agent-sudo init-approval
```

---

## 3. Implementation approach

- **New module `agent_sudo/routing_check.py`** producing a list of grouped, typed signals:
  ```
  Signal(section, status: OBSERVED | LIMITATION | MISCONFIG, label, detail)
  ```
  with a `format_routing_report(signals)` renderer. Mirrors the existing `DoctorCheck` / `format_doctor_checks` shape in [doctor.py](../../agent_sudo/doctor.py) so the style is consistent.
- **Reuse, don't rebuild:**
  - Config/workspace/policy: `CONFIG_PATH`, `load_approval_config` ([approvals.py](../../agent_sudo/approvals.py)), workspace from [context.py](../../agent_sudo/context.py), policy check from [doctor.py](../../agent_sudo/doctor.py).
  - Activity + integrity: `read_audit_entries` and `verify_audit_log` ([audit.py](../../agent_sudo/audit.py)). Derive count, last timestamp, and a decision histogram from the entries.
  - Audit-log location: check the workspace `.agent-sudo/mcp-audit.jsonl` and `~/.agent-sudo/mcp-audit.jsonl`; report which was found.
- **Client-config reader (best-effort, isolated, never throws to the user):** a small helper with a table of known client config paths (Claude Desktop macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`; leave hooks for Cursor/others). Parse JSON, read `mcpServers`:
  - agent-sudo present? → `✓ registered`.
  - other server keys → `⚠ other MCP servers present` (list names). Heuristic-only "may expose tools" note when a name/command contains tokens like `file`, `fs`, `shell`, `bash`, `exec`, `cmd`, `net`, `fetch`, `http`. **Heuristic is informational; never asserted as fact.**
  - file unreadable/absent → `⚠ client config not found (best-effort)` — *not* an error, since the user may use a client we don't know how to read.
- **Standing trust-boundary block:** a fixed set of `⚠` lines emitted unconditionally.
- **CLI wiring:** add `verify-routing` subparser + handler in [gateway.py](../../agent_sudo/gateway.py) next to `doctor` (~ the 3-line pattern at gateway.py:840). Add a one-line pointer from `doctor`'s output.
- **Exit code:** informational by default → `0` even with `⚠`. Optional `--strict` returns non-zero only on provable `✗` misconfig (e.g. approvals not initialized) or no-audit-log-found, for CI/scripted setup checks. The trust-boundary `⚠` lines never affect exit code.
- **No new dependencies. No behavior change to gating.** This is a read-only reporter over existing state.

---

## 4. Limitations (carried into the docs, not just the code)

- The MCP-client parse is **macOS/Claude-Desktop-first and best-effort**; absence of a recognized config is reported neutrally, not as a problem.
- "Other MCP servers may bypass" is a **name/command heuristic**, never a capability assertion — a server named `notes` could expose shell, and one named `shell-runner` could be a sandbox. The wording must stay hedged.
- The whole command is **observational**: it raises confidence when signals are present and lowers it when they're absent, but it **cannot certify routing completeness**. The closing disclaimer is mandatory, not decorative.
- It does not (and must not be extended to) intercept live traffic or probe the client — that would be scope creep toward an execution framework, which is explicitly off the table.

---

## 5. Test plan (`tests/test_routing_check.py`)

1. **Activity parsing.** Temp audit log with N mixed-decision records → report shows `N records`, correct histogram, a last-timestamp line.
2. **Integrity surfaced.** Intact chain → `✓ audit integrity verified`; tamper one record → `⚠`/`✗ integrity` (reuse `verify_audit_log`).
3. **Empty / missing log.** No log → `⚠ no requests observed yet` (and exit 0 without `--strict`).
4. **Config reflected.** approvals present/absent → `✓` / `✗ not initialized`; workspace present/absent likewise.
5. **Client-config parse.** Fake config with agent-sudo + another server → `✓ registered` + `⚠ other MCP servers present` listing it; missing file → neutral `⚠ not found`, never a raised exception.
6. **Boundary block always prints.** Even on a fully-healthy fixture, the `Trust boundary` `⚠` lines are present.
7. **Over-claim guardrail (the important one).** Assert the rendered output **never contains** a forbidden phrase — `"you are protected"`, `"fully protected"`, `"you're safe"`, `"guaranteed"` (case-insensitive). This test is the executable form of the hard constraint.
8. **Exit codes.** Default `0` with warnings; `--strict` non-zero only on provable misconfig / no audit log.

---

## 6. Expected user workflow

1. Install, `init-approval`, `workspace set`, wire the MCP server.
2. `agent-sudo verify-routing` → config `✓`, but `⚠ no requests observed yet`.
3. Ask the agent to do something (e.g. read a file, run a command).
4. `agent-sudo verify-routing` again → `✓ requests observed`, `✓ integrity verified`, last decision timestamp, decision histogram.
5. Read the `Trust boundary` `⚠` block and the `other MCP servers` warning → understand that bypassing tools must be disabled or routed, and that this command confirms *activity*, not *completeness*.
6. To confirm one specific action was gated: perform it, then `agent-sudo audit list` and look for it (the existing, authoritative check this command points to).

---

## 7. Why this is the right increment

It strengthens the exact value proposition reviewers keep circling — *"Agent_Sudo only protects what flows through it"* — by making that boundary **observable and honest** instead of inferred. It adds no execution surface, no new dependency, and no gating behavior; it is a read-only reporter that turns the manual `audit list` ritual into a structured, self-limiting status command. Crucially, its design center is *refusing to overclaim* — which is both the correct security posture and consistent with the messaging work already shipped (#27).
