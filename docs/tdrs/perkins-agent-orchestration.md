---
tdr: "1.0"
id: "perkins-agent-orchestration"
title: "Perkins Agent Orchestration with deepagents and LangGraph"
summary: "The Master Orchestrator is a deepagents agent using LangGraph with SqliteSaver checkpointing."
---

# rules

## Master Orchestrator

- The Master Orchestrator MUST be created with `create_deep_agent()` from the `deepagents` library.
- The Master uses `SqliteSaver` (from `langgraph-checkpoint-sqlite`) as its checkpointer, stored at `.perkins/sessions/{session-id}/graph.db`.
- Each session has a unique `thread_id` equal to the session ID (e.g. `perk_a3f9c2`); this thread ID is used for all `invoke()` and `Command(resume=...)` calls within the session.
- All `invoke()` calls on the Master graph MUST pass `version="v2"`.
- Answer Agents are deepagents subagents registered on the Master via the `subagents=[...]` parameter.

## Human escalation (ask_master)

- When the Master cannot answer a dev sub-agent question from its loaded context, it MUST trigger `interrupt()` with the question payload.
- The `interrupt()` value MUST be structured as `{"type": "ask_master", "issue_id": str, "question": str, "context": str}`.
- The CLI chat interface resumes the Master with `Command(resume={"answer": str})`.
- The Master MUST NOT invent answers to dev sub-agent questions — it either answers from context or escalates.

## Answer Agents

- Answer Agents are deepagents subagents with a single responsibility: post to and poll GitHub issue threads.
- They are defined as `subagents=[{"name": "answer-agent-{issue_id}", ...}]` and spawned by the Master when escalation is needed.
- Answer Agents do NOT have access to cliplin MCP tools — communication only.

## Context compaction

- The Master monitors approximate token usage in its context window.
- On approaching the threshold defined in `perkins.yaml` (`session.compaction_threshold`, default `0.80`), the Master summarizes its state and stores it at `.perkins/sessions/{session-id}/compaction/snapshot-{timestamp}.md`.
- Context is rebuilt from: project context > active flow states > pending escalations > recent events.
- Compaction is a LangGraph node triggered by the Master's token usage check, not an external signal.

## Cliplin environment inheritance

The Master Orchestrator MUST inherit the full cliplin environment of the project at
initialization time. This ensures the Master answers dev sub-agent questions using
the same context and rules that a human developer would have available.

### MCP servers

- The Master reads `.mcp.json` from the project root on initialization.
- MCP server entries are converted to `StdioConnection` dicts and passed to
  `MultiServerMCPClient` from `langchain-mcp-adapters`.
- `await client.get_tools()` returns `list[BaseTool]`; these are passed as
  `tools=[...]` to `create_deep_agent()`.
- `.mcp.json` format expected: `{"mcpServers": {"name": {"command": "...", "args": [...]}}}`.
- If `.mcp.json` is absent or malformed, a warning is logged and initialization
  continues without MCP tools (the Master will escalate all unknown questions to
  the human via `interrupt()`).

### AI tool rules

The Master detects the configured AI tool from `perkins.yaml`
(`dev_agents.default_tool`) and loads the corresponding rules into the Master's
system prompt:

| `default_tool`  | Rules directory        | Files loaded                          |
|-----------------|------------------------|---------------------------------------|
| `claude-code`   | `.claude/rules/`       | all `*.md` files                      |
| `gemini`        | `.gemini/`             | all `*.md` files                      |
| `cursor`        | `.cursor/rules/`       | all `*.mdc` files (newer format)      |
|                 | `.cursorrules`         | single file (legacy, if dir absent)   |

- Rules are concatenated and passed as the system prompt prefix to
  `create_deep_agent()`.
- For `cursor`: prefer `.cursor/rules/*.mdc`; fall back to `.cursorrules` if the
  directory does not exist.
- If neither rules source exists for the configured tool, a warning is logged and
  initialization continues without rules.
- Rules are loaded once at startup; changes to rule files require a session restart.

### Context queries on ask_master

When the Master receives an `ask_master` call:

1. Query `technical-decision-records` collection using the question verbatim as
   `query_text` via `context_query_documents`.
2. If no result found, query `features` collection.
3. If a result is found in either collection, include it in the graph input and
   let the LangGraph node decide if it is sufficient to answer.
4. If the graph node cannot answer (returns `__interrupt__`) AND `search.enabled=false`
   (or absent) in `perkins.yaml`, escalate to human via `interrupt()` immediately.
5. If the graph node cannot answer AND `search.enabled=true` in `perkins.yaml`:
   - Perform a web search using the question as the query (see `docs/tdrs/perkins-search.md`).
   - If the search returns results, invoke the graph a second time with the results
     appended to the context.
   - If the graph answers on the second invocation → return directly to the sub-agent;
     do NOT escalate to the human.
   - If the graph raises `__interrupt__` again after the second invocation, OR if the
     search failed/returned no results → escalate to human via `interrupt()` with
     `web_search_results` included in the payload (see `perkins-search.md` for payload
     structure).
