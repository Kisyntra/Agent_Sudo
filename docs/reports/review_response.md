# Security Review Response

This document summarizes the external security review feedback incorporated after `v0.3.0-beta`.

## Accepted Feedback

### Phrase Detection Is Not A Boundary

Accepted.

Documentation now states that phrase detection is not a security boundary. The actual boundary is provenance + policy + mandatory routing through `PermissionGateway.evaluate()`.

Phrase detection remains only as a convenience catch for obvious malicious instructions such as requests to bypass policy, reveal secrets, or exfiltrate tokens.

### Explicit Sandbox Limitation

Accepted.

The README and architecture docs now state that agent-sudo is not a sandbox. It does not isolate processes, enforce kernel-level controls, or protect calls that bypass the gateway.

### Stronger Write-File Risk Model

Accepted.

`write_file` and `edit_file` remain `SENSITIVE` for ordinary documents. They are upgraded to `CRITICAL` for executable or runtime-control targets:

- `*.sh`
- `*.bash`
- `*.zsh`
- `*.py`
- `*.js`
- `*.ts`
- `*.rb`
- `*.pl`
- `.zshrc`
- `.bashrc`
- launchd plists
- cron files
- systemd units
- MCP configs
- runtime configs

Tests were added for these upgrade cases.

### Architecture Documentation

Accepted.

`docs/ARCHITECTURE.md` now documents the request flow:

```text
Native Tool Call
-> Adapter
-> ActionRequest
-> Provenance
-> Classifier
-> Policy
-> Delegation
-> Approval / Pending Approval
-> Audit
-> Executor
```

It also explains the `PermissionGateway.evaluate()` decision flow and clarifies where execution happens.

## Rejected Feedback

No review feedback was rejected in this pass.

Some broader hardening ideas were not implemented because they would be major new features rather than release hygiene changes.

## Limitations

- agent-sudo is not a sandbox.
- agent-sudo only protects calls routed through its gateway.
- Direct shell, file, browser, email, desktop, or network access can bypass it.
- Phrase detection is incomplete by design and should not be treated as prompt-injection protection by itself.
- The default policy is a small local baseline, not an enterprise policy engine.
- Pending approvals are local JSON-backed state and should not be committed.
- Audit hash chaining makes tampering detectable when the log is available; it does not make local files impossible to delete or replace.

## Future Roadmap

- Expand adapter coverage for more native tool schemas.
- Add more precise target classification for package managers, service managers, and agent runtime configs.
- Support richer policy configuration without weakening the default local-only model.
- Add deployment guidance for mandatory routing in common agent runtimes.
- Add more integration tests for real MCP clients and non-interactive approval retries.
- Add optional stronger local storage protections for approval and delegation state.
