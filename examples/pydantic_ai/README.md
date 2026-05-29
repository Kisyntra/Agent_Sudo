# PydanticAI Integration Example

This example demonstrates how to integrate `Agent_Sudo` as a local, type-safe permission gate within a `pydantic-ai` application.

## Key Pattern: In-Process Tool Decorator

PydanticAI tools are registered via decorators like `@agent.tool`. To enforce policies, we wrap the tool implementation with an `Agent_Sudo` decorator that evaluates permissions *before* the core function executes.

## Quickstart

Run the example:

```bash
python3 example.py
```

## How It Works

1. **Policy Load**: The script initializes `PermissionGateway` with the local policy rules.
2. **Interception**: When the agent attempts to invoke a tool, the `@agent_sudo_gate` wrapper constructs an `ActionRequest` from the function arguments.
3. **Authorization**: The gateway evaluates the request. If the decision is `DENY`, the wrapper raises a `PermissionError`, halting execution and preventing the tool from running.
