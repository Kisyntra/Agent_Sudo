# Release Notes: Agent_Sudo v0.5.2

Patch release. Tightens sensitive read/search and mutation blocking, adds a recent audit review command, and makes delegation-store mismatches easier to diagnose. No new runtime dependencies.

## Security / Policy Hardening

- **Sensitive read/search hardening.** Blocks sensitive `read_file` and `search_files` targets more consistently, including macOS Keychains, Messages, Mail, Cookies, and Safari stores; browser cookie/login profile stores; gcloud and kube config directories; and common credential files such as `.netrc`, `.npmrc`, and `.pypirc`.
- **Git/GitHub mutation hardening.** Blocks mutating Git and GitHub CLI shell commands at the classifier and executor boundary, including `git push`, `git remote` mutations, mutating `gh issue`/`pr`/`release`/`repo`/`workflow`/`run` commands, and mutating `gh api` calls.
- **Read-only command compatibility.** Read-only Git/GitHub commands remain approval-gated rather than hard-denied.

## Audit UX

- **Recent audit review.** Adds `agent-sudo audit review`, which verifies the audit chain, summarizes recent decision counts, and lists non-ALLOW records for a configurable window such as `30m`, `24h`, or `7d`.

## Delegation Diagnostics

- **Delegation store visibility.** Keeps `agent-sudo delegate create` stdout as parseable token JSON while reporting the delegation file path on stderr.
- **Default-store warning.** When `delegate create` uses the default `~/.agent-sudo/delegations.json` store, the CLI warns that integrations may read a different delegation store.
- **Integration docs.** Adds Hermes delegation-store guidance using explicit `--delegations-file`.
- **Troubleshooting checklist.** Adds a "delegation created but authorization still denied" checklist covering action, path, actor, expiry, use count, and delegation-file mismatches.

## Compatibility

- No new runtime dependencies.
- Delegation token format is unchanged.
- Existing JSON stdout consumers of `agent-sudo delegate create` remain compatible.
