# Release Notes: Agent_Sudo v0.5.3

Minor release. Ships the README v2 repositioning and aligned public metadata, plus the first two Audit Explorer features (`audit list` filters + origin column, and token-first `audit trace`). No breaking changes, no schema changes, no policy-behavior changes, no new runtime dependencies.

## Positioning

- **README repositioning.** Agent_Sudo is framed as an authorization, delegation, provenance, and verifiable-audit engine for AI agents. MCP is how you connect it, not what it is.
- **Public metadata aligned.** The PyPI `Summary` and the MCP Registry `server.json` description carry the same authorization / delegation / provenance / verifiable-audit positioning, so PyPI, the MCP Registry, third-party indexes, and crawlers surface consistent framing.

## Audit Explorer

- **`audit list` filters + origin column.** `agent-sudo audit list` adds `--since`, `--decision`, `--origin`, `--actor`, `--tool`, `--target`, and `--non-allow`, and shows a provenance origin column. The flat decision log becomes filterable and the instruction origin is visible per row. `--json` output shape is unchanged; with no filters, behavior matches v0.5.2.
- **`audit trace <token_id>`.** Token-first delegation lifecycle inspection. Resolves a delegation token by full id or unique prefix, joins its store metadata (scope, max-uses, uses, expiry, revoked) with every audit reference, and reports observed consumes/denials plus the causes the denial reasons cite, with a raw-reason fallback. Read-only; store-state and log-observed quantities are reported separately and are never claimed as exact usage counts, intended tokens, or definitive causality.

## Compatibility

- No breaking changes.
- No schema changes (`delegations.json` and `audit.jsonl` formats unchanged).
- No policy-behavior changes (classifier/policy decisions are identical to v0.5.2).
- No new runtime dependencies.
- New CLI surface is additive: `audit list` filter flags and the `audit trace` subcommand.
