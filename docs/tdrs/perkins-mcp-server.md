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

## ask_master asyncio bridge pattern

When `ask_master` is called and the Master cannot answer from context, the tool handler MUST use the following asyncio suspension pattern:

1. The tool handler invokes the Master graph, which runs until `interrupt(payload)` is raised inside a node.
2. LangGraph saves the interrupted state to `SqliteSaver` and returns control to the caller.
3. The tool handler places the interrupt payload on a per-issue `asyncio.Queue` keyed by `(session_id, issue_id)` stored in the Master Orchestrator.
4. The tool handler awaits a separate per-issue response `asyncio.Queue`.
5. `perkins chat` reads from the interrupt queue, presents the question to the human, and places the answer on the response queue.
6. The tool handler dequeues the answer, calls `graph.invoke(Command(resume={"answer": answer}), version="v2")`, and returns the answer to the dev sub-agent.

The Master Orchestrator MUST maintain two dicts: `interrupt_queues: dict[str, asyncio.Queue]` and `answer_queues: dict[str, asyncio.Queue]`, keyed by `issue_id`.

## report_progress tool

- `report_progress` MUST append a progress entry to the flow's JSON file at `.perkins/sessions/{session-id}/flows/{issue_id}.json`.
- Each entry is appended to a `progress_entries` array in the flow JSON with the structure: `{"timestamp": "<ISO-8601>", "message": "<string>"}`.
- The write MUST be atomic (write to `.tmp` then rename) to avoid partial writes.

## get_task_context tool

- `get_task_context` MUST return a payload containing: the GitHub issue body, the current flow state from the flow JSON, and the content of the most recent compaction snapshot at `.perkins/sessions/{session-id}/compaction/` (if any exists).
- The issue body is read from the flow JSON `issue_body` field if already cached; otherwise it is fetched via the `gh` CLI and cached into the flow JSON.
- If no compaction snapshot exists, the `compaction_snapshot` field in the response is `null`.
