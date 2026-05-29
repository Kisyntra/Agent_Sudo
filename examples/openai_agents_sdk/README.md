# OpenAI Agents SDK Integration Example

This example demonstrates how to secure tool execution in applications built with the OpenAI Agents SDK (or assistant functions) using `Agent_Sudo`.

## Key Pattern: Pre-wrapped Tool Functions

OpenAI's SDK handles tool execution by running Python functions mapped to JSON schemas. By wrapping these Python functions with the `Agent_Sudo` gateway before providing them to the agent, we guarantee that the LLM cannot execute unauthorized tools even if it attempts to call them.

## Quickstart

Run the example:

```bash
python3 example.py
```

## How It Works

1. **Decorator Integration**: The `@agent_sudo_gate` wrapper converts the standard arguments sent by the OpenAI assistant into an `ActionRequest`.
2. **Policy Check**: The `PermissionGateway` evaluates the request.
3. **Execution Guard**: If allowed, the function executes and returns the output to the assistant. If denied, a `PermissionError` is raised, returning an error response to the assistant instead of running the dangerous side-effect.
