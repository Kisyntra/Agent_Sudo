# Release Notes: Agent_Sudo v0.5.4

Patch release. Publishes the onboarding and evaluation work that had been merged to `main` but never shipped to PyPI. Most importantly, it ships `agent-sudo eval` — the published "fastest path" that the README and the 5-minute evaluator guide already advertise. On v0.5.3 a fresh `pipx install agent-sudo-mcp && agent-sudo eval` failed with `invalid choice: 'eval'`; this release fixes that. No breaking changes, no schema changes, no policy-behavior changes, no new runtime dependencies.

## Evaluation

- **`agent-sudo eval` one-shot evaluator.** Runs the full loop — a critical shell request is blocked, a one-use scoped delegation allows it exactly once, the repeated request is denied after the token is exhausted, and the hash-chained audit log verifies — in a single command, and prints a PASS/FAIL ladder:

  ```text
  [1/5] Blocked unsafe request ........ PASS
  [2/5] Created delegation ............ PASS
  [3/5] Delegated request allowed ..... PASS
  [4/5] Token exhausted, denied again . PASS
  [5/5] Audit chain verified .......... PASS

  Result: PASS
  ```

  It runs in a temporary directory and **never reads or writes the user's `~/.agent-sudo` state**. It exits `0` only when all five steps pass (safe in CI). `--json` emits a machine-readable report; `--output-dir DIR` writes the artifacts to a location you choose.

## Onboarding

- **Claude Code + Codex CLI setup paths.** `agent-sudo setup` adds a `claude-code` target alongside `codex`, `claude-desktop`, `hermes`, and `openclaw`. The headline audience now has a first-party setup path.
- **Interactive `setup` selector.** `agent-sudo setup` with no target presents an interactive picker; targets are also selectable by number or by name. Bare invocations are guided rather than erroring.
- **Generated MCP config pins absolute paths and approval flags.** Setup output pins absolute `--audit-log`, `--delegations-file`, and `--pending-approvals-file` paths plus the macOS approval flags, so a configured client's state lands in predictable locations instead of relative defaults.
- **First-run friction removed.** The built-in demo's first scenario is now correctly labeled `Sensitive Read (REQUIRE_APPROVAL)`, with related first-run copy fixes.

## Documentation

- **CLI command reference** added; the `audit review` flag documentation is corrected.

## Cosmetic

- **Compact gated wordmark** printed by interactive commands.
- **MCP registry description** in `server.json` shortened to satisfy registry length limits.

## Compatibility

- No breaking changes.
- No schema changes (`delegations.json` and `audit.jsonl` formats unchanged).
- No policy-behavior changes (classifier/policy decisions are identical to v0.5.3).
- No new runtime dependencies.
- New CLI surface is additive: the `eval` command, the `setup claude-code` target, and the interactive `setup` selector.
