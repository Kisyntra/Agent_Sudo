# Release Notes: Agent_Sudo v0.5.0

> **⚠️ Behavior change — review before upgrading.** Requests that do not attest a
> trust level are now treated as untrusted. Integrations that speak for the
> operator must send `source_trust="USER_DIRECT"` explicitly, or previously-allowed
> SAFE actions will now be escalated to `REQUIRE_APPROVAL`.

This release is a minor version bump because it changes default trust behavior in a
backward-incompatible way (fail-closed provenance), in addition to adding new
read-only tooling, a real end-to-end example, and distribution automation.

## Security

- **Fail-closed provenance (behavior change, #28).** A request that does not assert
  a trust level — no `source_trust`, no `provenance` — is now treated as `UNKNOWN`
  (untrusted) instead of `USER_DIRECT`. The change is applied at the MCP JSON-RPC
  boundary (`tool_call_from_jsonrpc`), the `ActionRequest.from_dict` path, and the
  `ActionRequest` constructor default. A SAFE action (e.g. `read_file`) arriving
  without provenance is now escalated to `REQUIRE_APPROVAL` rather than allowed
  silently. Explicit `USER_DIRECT` is honored exactly as before.
- **Provenance consistency reconciliation (#30).** When a request asserts a
  `source_trust` higher than its `source` / `origin_type` evidence supports (e.g.
  `source="webpage"` paired with `source_trust="USER_DIRECT"`), the gateway now
  downgrades the trust to the most restrictive level the evidence supports and
  records an `inconsistent_provenance` reason on the decision and audit entry.
  Internally consistent provenance is honored exactly as before.

## Features

- **`agent-sudo verify-routing` (#31).** A read-only command that reports observed
  evidence of whether actions are flowing through Agent_Sudo: configuration state,
  observed gateway activity (audit record count, last record, decision histogram,
  hash-chain integrity), a best-effort scan of the client MCP config for
  bypass-capable servers, and the standing trust-boundary limits. It performs no
  probing, execution, or telemetry, and deliberately makes no aggregate
  "you are protected" claim.

## Documentation

- **Messaging accuracy (#27).** Security messaging is aligned with provenance-based
  enforcement across the README, Claude Desktop guide, and security model.
- **Evaluator activation path.** First-time MCP evaluators are now directed to one
  primary path: blocked -> delegated -> allowed once -> blocked again -> audit
  verified. The flow uses existing MCP server, delegation, audit-listing,
  audit-verification, and routing-verification functionality only.

## Examples

- **PydanticAI end-to-end dogfood (#34).** A real, deterministic, offline example: a
  `FunctionModel`-driven agent loop exercises the full path — agent →
  `PermissionGateway` → real temp-dir file I/O → scoped delegation → hash-chained
  audit → audit verification — across four scenarios (safe allow; sensitive write
  held then allowed via a delegation token; blocked exfiltration; audit chain
  verified). The LLM is a deterministic test double (no key, no network); the
  gateway/delegation/audit path and file I/O are real. Adds a `pydantic-ai`
  `examples` optional extra (never a runtime dependency) and a dedicated CI job; the
  example test skips cleanly when the extra is absent.

## Distribution & Ecosystem

- **Official MCP Registry publication.** `io.github.Kisyntra/agent-sudo-mcp` is
  published and active in the official MCP Registry.
- **PyPI Trusted Publishing (OIDC).** Releases publish to PyPI via OIDC Trusted
  Publishing, removing long-lived API tokens from the release path.

## Maintenance

- Stabilizes the approval-helper opener test by replacing a brittle substring scan
  with a deterministic structural assertion (no production behavior change).

## Known Limitations

- A consistently-forged `USER_DIRECT` (where `source`/`origin_type` agree but are
  fabricated) is still believed, pending host attestation / nonce binding. The
  fail-closed and reconciliation changes above close the *absent* and *inconsistent*
  provenance cases, not the *consistently-forged* one.
- The MCP `write_file` (scoped to `/tmp/agent-sudo-demo`) and `run_shell_command`
  (narrow allowlist) tools are demo executors, not a turnkey way to mediate a
  client's real file/shell tools.
