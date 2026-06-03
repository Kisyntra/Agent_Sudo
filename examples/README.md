# Examples

All examples use fake actors, fake paths, and placeholder `.invalid` email addresses.

- `demo_requests.json`: mixed request list showing safe, sensitive, critical, and blocked decisions.
- `generic_tool_call.json`: universal schema example with an unknown tool that requires approval.
- `codex_tool_call.json`: native-style file edit request for a code-oriented agent.
- `hermes_tool_call.json`: native-style shell request for an agent runtime.
- `claude_desktop_tool_call.json`: desktop-agent file edit request.
- `mcp_tool_call.json`: MCP-style browser click request.
- MCP gateway examples should route through `agent_sudo.mcp_gateway.MCPGateway`; the demo executor only supports local `read_file`, `/tmp/agent-sudo-demo` writes, and a small shell allowlist.
- `provenance_user_direct.json`: authenticated user-direct provenance example.
- `provenance_external_content.json`: external webpage provenance example.
- `strict_policy.yaml`: stricter sample policy.
- `local.example.yaml`: fake local setup example showing ignored local config locations.

## Framework Integration Examples

These examples demonstrate how to integrate the `Agent_Sudo` authorization/provenance engine in-process within popular Python agent frameworks:

- **[pydantic_ai/](pydantic_ai/)**: Gating tools inside `pydantic-ai` applications using Python decorators.
- **[openai_agents_sdk/](openai_agents_sdk/)**: Pre-wrapping tool functions passed to the OpenAI Agents SDK.
- **[langgraph/](langgraph/)**: Securing tool nodes and graph runner flows inside LangGraph agent graphs.
- **[agent_runtimes/](agent_runtimes/)**: Registering the native `agent_sudo_local` hook plugin in the `agent-runtimes` package.
