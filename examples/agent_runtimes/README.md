# agent-runtimes Integration Example

This example demonstrates how to configure and register the `Agent_Sudo` local authorization/provenance plugin within the `agent-runtimes` ecosystem.

## Key Pattern: Configuration and Tool Hooks

The `agent-runtimes` package registers `Agent_Sudo` as a local tool execution hook handler (`agent_sudo_local`). 
Instead of wrapping individual functions in python code, you register the hook inside the runtime's configuration profile. The runner automatically intercepts all registered tools prior to execution.

## Quickstart

Verify the example configuration and run the diagnostic mock:

```bash
python3 example.py
```

## Configuration Schema

```yaml
tool_hooks:
  # Path configuration for local policy rules
  agent_sudo_policy_path: "policy.yaml"

  # Target audit log file
  agent_sudo_audit_log_path: "audit.jsonl"

  # Intercept tool calls prior to execution
  before_tool_execute:
    - handler: agent_sudo_local
```
