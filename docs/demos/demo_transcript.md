# agent-sudo End-to-End Demo Transcript

Audience: GitHub readers, blog posts, conference demos, and security review.

This transcript is based on the validated MCP workflow. The local home path is redacted as `~/agent-sudo`.

## Setup

The agent has an MCP tool named `run_shell_command`, exposed by `agent-sudo-mcp`.

Default policy:

- `run_shell_command` is `CRITICAL`.
- Critical actions require strong approval.
- Non-interactive MCP clients cannot self-approve.
- Scoped delegation can allow a narrow action temporarily.

## Step 1: Agent Requests Shell

Incoming MCP tool call:

```json
{
  "actor": "codex",
  "tool": "shell",
  "action": "run_shell_command",
  "target": "pwd"
}
```

agent-sudo evaluation:

```text
classification: CRITICAL
decision: REQUIRE_STRONG_APPROVAL
executed: false
```

Interpretation:

The command is harmless-looking, but shell access is powerful. agent-sudo refuses to execute it without strong approval or a scoped delegation.

## Step 2: User Grants One Narrow Delegation

Delegation:

```text
actor: codex
action: run_shell_command
target: pwd
max uses: 1
critical: true
```

Interpretation:

The user did not grant broad shell access. The agent can run only `pwd`, only as `codex`, only once.

## Step 3: Agent Retries The Same Request

Incoming MCP tool call:

```json
{
  "actor": "codex",
  "tool": "shell",
  "action": "run_shell_command",
  "target": "pwd"
}
```

agent-sudo evaluation:

```text
classification: CRITICAL
decision: ALLOW
approval_method: DELEGATION
executed: true
stdout: ~/agent-sudo
```

Interpretation:

The request matches actor, action, target, and critical delegation scope. agent-sudo executes it and consumes the single allowed use.

## Step 4: Agent Tries Again

Incoming MCP tool call:

```json
{
  "actor": "codex",
  "tool": "shell",
  "action": "run_shell_command",
  "target": "pwd"
}
```

agent-sudo evaluation:

```text
classification: CRITICAL
decision: DENY
executed: false
reason: delegation token is exhausted
```

Interpretation:

The token was single-use. The repeated request is blocked.

## Audit Trail

Expected audit decisions:

```text
1. REQUIRE_STRONG_APPROVAL
2. ALLOW via DELEGATION
3. DENY because delegation token is exhausted
```

Each audit entry is chained with `previous_hash` and `entry_hash`, so tampering can be detected with:

```bash
agent-sudo verify-audit .agent-sudo/mcp-audit.jsonl
```

## Demo Takeaway

agent-sudo turns tool access into a local checkpoint:

- classify the action
- apply policy
- require approval or scoped delegation
- execute only after `ALLOW`
- record every decision

The pattern is simple: one local gateway, any agent, every tool call checked.
