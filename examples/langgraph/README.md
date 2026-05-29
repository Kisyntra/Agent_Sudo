# LangGraph Integration Example

This example demonstrates how to integrate `Agent_Sudo` within a `langchain-ai/langgraph` agent execution graph.

## Key Pattern: Safe Tool Node Execution

In LangGraph, tools are typically executed inside a centralized node (such as the prebuilt `ToolNode`). To integrate `Agent_Sudo` cleanly:
1. **Tool-Level Wrapping**: Wrap the tool functions with the gateway decorator before passing them to the `ToolNode`.
2. **Node-Level Interception**: Run a custom node handler that acts as the permission gateway interceptor.

## Quickstart

Run the example:

```bash
python3 example.py
```

## How It Works

1. **Decorator Hook**: `@agent_sudo_gate` intercepts tool execution within the graph node.
2. **State Context**: LangGraph manages the state dict. The gateway validates individual tool calls extracted from the agent's message payload.
3. **Execution Routing**: If the gateway returns `DENY`, execution halts, raising a `PermissionError`. In a production setup, this error is caught, and the node writes the error back to the graph state to let the LLM react or explain the restriction.
