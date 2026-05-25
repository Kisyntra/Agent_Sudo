# Install For Agents

This document is for users who want to give this repository to a local or desktop AI agent and ask it to install or configure `agent-sudo`.

## Important Limits

`agent-sudo` cannot override an agent's system prompt.
It cannot force an agent to behave safely if the agent can still call dangerous tools directly.

Real protection requires routing tool execution through `agent-sudo`.
If an agent keeps direct access to shell, browser, email, messaging, file-write, or credential tools, `agent-sudo` is advisory, not enforced.

Where possible:

- remove direct dangerous tools from the agent runtime
- restrict direct tool permissions
- replace direct tool calls with an `agent-sudo` wrapper or proxy
- verify every route with dry-run before enabling execution

## Safe Install Request

Give the agent [AGENT_INSTALL_PROMPT.md](AGENT_INSTALL_PROMPT.md).

The agent should:

1. install the package locally
2. run `agent-sudo doctor`
3. run `agent-sudo init-approval`
4. run demo checks in dry-run mode
5. show the user what tool config files need manual edits
6. avoid reading or printing secrets

## Setup Commands

The setup commands are dry-run checklists.
They do not edit agent config automatically.

```bash
agent-sudo setup hermes
agent-sudo setup codex
agent-sudo setup claude-desktop
agent-sudo setup openclaw
```

Each command prints:

- what config files or runtime settings to inspect
- what dangerous direct tools to remove or restrict
- what wrapper or proxy route to use
- a verification command

## Doctor

Run:

```bash
agent-sudo doctor
```

The doctor checks:

- approval config exists
- default policy exists
- audit log path is writable
- delegation store path is writable
- personal-data scanner passes
- Python version is supported

The approval config check may warn before `agent-sudo init-approval` has been run.
