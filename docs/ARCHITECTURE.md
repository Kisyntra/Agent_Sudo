# Architecture

agent-sudo is a routing and policy gateway. It is not a sandbox, kernel boundary, container runtime, or filesystem isolation layer.

The security boundary is:

- provenance
- policy
- mandatory routing through the gateway before native tools execute

Keyword or phrase detection is not the security boundary. Phrase detection is only a convenience catch for obvious malicious instructions.

## Execution Path

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

## Components

### Native Tool Call

A native tool call is the original request from an agent runtime or MCP client, such as reading a file, writing a file, editing a file, or running a shell command.

### Adapter

Adapters normalize runtime-specific request shapes into agent-sudo's internal schema. The adapter layer is where Codex, Hermes, Claude Desktop, generic JSON, and MCP-style inputs become a common request format.

### ActionRequest

`ActionRequest` is the normalized request object. It records the actor, source, tool, action, target, payload summary, risk hints, trust level, and provenance.

### Provenance

Provenance describes where the request came from and how it was authenticated. It includes origin type, channel, authentication method, session ID, request ID, parent request ID, and delegation chain.

Provenance lets the gateway distinguish a direct user request from agent-internal work, external content, external APIs, and unknown sources.

### Classifier

The classifier maps an `ActionRequest` to one of:

- `SAFE`
- `SENSITIVE`
- `CRITICAL`
- `BLOCKED`

Classification is based on the requested action, target path, provenance, source trust, and explicit risk hints. Phrase detection can mark obvious malicious instructions as blocked, but phrase detection is not treated as the security boundary.

For file writes, ordinary documents remain `SENSITIVE`. Writes and edits are upgraded to `CRITICAL` when they target executable code, shell startup files, launchd plists, cron files, systemd units, MCP configs, or runtime configs.

For file reads, ordinary documents remain `SAFE` and are auto-allowed by default. However, reads targeting sensitive configuration directories (such as `~/.ssh/`, `~/.config/`, `~/.agent-sudo/`, `~/.agent-runtime/`), env files (`.env`, `.env.*`), or paths/filenames containing keywords like `auth`, `token`, `credential`, `secret`, `private_key`, or `api-key` are upgraded to `BLOCKED` and denied by default.

### Policy

Policy converts classification into a gateway decision:

- `SAFE` -> `ALLOW`
- `SENSITIVE` -> `REQUIRE_APPROVAL`
- `CRITICAL` -> `REQUIRE_STRONG_APPROVAL`
- `BLOCKED` -> `DENY`

The default policy is intentionally small and local. It should be treated as a baseline, not a complete enterprise policy engine.

### Delegation

Delegation is a scoped local token that can allow a matching action without prompting again. Delegations are constrained by actor, action, target path, expiry, use count, and whether critical actions are allowed.

Delegation is checked before interactive approval. A matching delegation can allow the request. An exhausted or mismatched delegation cannot.

### Approval / Pending Approval

Sensitive actions require local approval. Critical actions require the local approval passphrase.

For non-interactive MCP clients, agent-sudo cannot safely prompt inside the client process. Approval-required MCP calls create pending approval requests instead. The user approves or denies from a local terminal, then the MCP client retries the matching tool call. Approved pending requests are consumed once.

### Audit

Every gateway decision can be written to a JSONL audit log. Audit entries include the request, classification, decision, approval method, reason, provenance, and hash-chain metadata.

Lifecycle events such as pending approval creation, approval, denial, expiration, and use can also be recorded.

### Executor

The executor runs only after the final gateway decision is `ALLOW`. If classification or policy requires approval and no valid approval or delegation exists, the executor does not run.

The executor layer is deliberately small in the current beta. The main enforceable MCP surface exposes `read_file`, `write_file`, and `run_shell_command`.

## PermissionGateway.evaluate() Flow

`PermissionGateway.evaluate()` is the core decision point:

1. Classify the normalized `ActionRequest`.
2. Convert the classification to a policy decision.
3. If the decision requires approval, check for a matching scoped delegation.
4. If delegation does not allow the request, handle approval:
   - interactive local flows can prompt for approval or passphrase confirmation.
   - non-interactive MCP flows can create or consume pending approvals.
   - external content cannot approve or escalate itself.
5. Build a `GatewayResult` with classification, decision, reason, approval method, approval attempts, pending approval metadata, and dry-run state.
6. Write the decision to the audit log when auditing is configured.
7. Return the result to the caller.

Execution happens outside `evaluate()`, after the caller checks that the final decision is `ALLOW`.

## Boundary And Limitations

agent-sudo only protects calls that are routed through it. If an agent still has direct access to shell, file, browser, email, desktop, or network tools, those direct tools can bypass agent-sudo.

The boundary is mandatory routing plus provenance and policy enforcement. Phrase detection is only a fallback catch for obvious malicious text and must not be relied on as a standalone defense.
