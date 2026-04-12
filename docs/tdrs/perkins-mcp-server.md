---
tdr: "1.0"
id: "perkins-mcp-server"
title: "perkins-master MCP Server"
summary: "The perkins-master MCP server is implemented using Anthropic's mcp Python SDK."
---

# rules

## MCP server implementation

- The `perkins-master` MCP server MUST be implemented using the **`mcp` Python SDK** (Anthropic's official SDK).
- The server exposes three tools to dev sub-agents: `ask_master`, `report_progress`, `get_task_context`.
- The server runs as an asyncio task within the Master Orchestrator process on the port specified in `perkins.yaml` (`mcp_server.port`, default `7331`).
- The server is started before the watcher loop and torn down on graceful shutdown.
- `ask_master` calls that the Master cannot answer from context MUST trigger a LangGraph `interrupt()` in the Master graph to escalate to the human (see `perkins-agent-orchestration.md`).
- Each tool call MUST be handled within the Master's asyncio event loop; no blocking calls.
