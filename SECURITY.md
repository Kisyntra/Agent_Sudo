# Security Policy

## Threat Model

`agent-sudo` is a local-only MVP permission gateway for AI agent tool execution.
It is designed to reduce risk from prompt injection, excessive agency, over-permissioned tools, missing approval boundaries, weak audit trails, and attempts to weaken local policy.

The project assumes external content is untrusted data, not instructions.
It does not assume that an agent can reliably distinguish a direct user instruction from injected content without explicit request metadata and policy checks.

## Local-Only Limitations

This MVP does not provide cloud identity, remote attestation, a database, centralized policy management, or tamper-proof storage.
Audit hash chains detect after-the-fact edits to a log file, but they do not prevent local deletion or replacement by a process with filesystem access.

Do not treat this project as a complete sandbox.
It is an enforcement and audit boundary that must sit in front of real tool execution.

## Reporting Vulnerabilities

Please report security issues privately to the project maintainers rather than opening a public issue with exploit details.
If no private channel is available yet, open a minimal issue saying that you have a security report, but do not include payloads, secrets, local paths, tokens, or private logs.

## Safe Disclosure

When reporting:

- describe the affected component
- include a minimal reproduction using fake fixtures only
- explain the expected and actual behavior
- do not include real credentials, personal data, audit logs, auth files, or private policy files

## No Secrets in Issues

Never paste secrets into public issues, pull requests, discussions, or logs.
This includes access tokens, refresh tokens, client secrets, auth files, local approval config, audit logs, and private policy files.
