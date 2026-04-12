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
