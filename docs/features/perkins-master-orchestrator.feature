@constraints
# governed_by:
#   - docs/tdrs/perkins-mcp-server.md
#   - docs/tdrs/perkins-agent-orchestration.md
#   - docs/tdrs/perkins-runtime-process.md
#   - docs/tdrs/perkins-serialization.md
#   - docs/tdrs/perkins-flow-lifecycle.md
#   - docs/tdrs/perkins-github-operations.md
# conflicts: []
# gaps:
#   - "Answer Agents (deepagents subagents for posting/polling GitHub issues) are out of scope — covered by a separate feature"
# escalation_triggers:
#   - "deepagents create_deep_agent() API signature differs from what the TDR assumes at implementation time — stop and verify before wiring"
#   - "mcp SDK server startup API differs from expected usage — stop and verify the correct asyncio integration pattern"
Feature: Perkins Master Orchestrator
  As the Perkins runtime,
  I want a real Master Orchestrator (deepagents + LangGraph) and MCP server (mcp SDK)
  wired into the asyncio event loop,
  So that dev sub-agents can coordinate autonomously, escalate questions to the human,
  report progress, and receive task context through a real coordination layer.

  # ── MCP SERVER ────────────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: MCP server starts as asyncio task on the configured port
    Given a valid PerkinsConfig with mcp_server.port 7331
    When runtime_main starts the Master Orchestrator
    Then an mcp Server asyncio task is created and started on port 7331
    And the mcp Server task is created before asyncio.create_task(watcher_loop(...)) is called

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: ask_master tool triggers LangGraph interrupt when Master cannot answer
    Given the MCP server is running and a dev sub-agent calls ask_master with issue_id "42" and question "Which pattern to use?"
    When the Master cannot answer from its loaded context
    Then interrupt is called with payload type "ask_master", issue_id "42", and the question text
    And the interrupt payload is placed on the interrupt_queue for issue "42"
    And the ask_master tool handler awaits the answer_queue for issue "42"

  @type:edge
  # why: TDR requires interrupt() only when Master cannot answer — if context is sufficient, the handler returns immediately without raising interrupt
  @status:implemented
  @changed:2026-04-12
  Scenario: ask_master tool returns answer directly when Master can answer from context
    Given the MCP server is running and a dev sub-agent calls ask_master with a question the Master can resolve
    When the Master resolves the question from its loaded context
    Then the ask_master tool handler returns the answer immediately
    And interrupt is not called

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: report_progress tool appends entry to flow JSON atomically
    Given the MCP server is running and a dev sub-agent calls report_progress with issue_id "42" and message "All tests passing"
    When the tool handler processes the call
    Then a progress entry {"timestamp": "<ISO-8601>", "message": "All tests passing"} is appended to the progress_entries array in flows/42.json
    And the write is performed atomically via a .tmp intermediate file

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: get_task_context returns cached issue body, flow state, and latest compaction snapshot
    Given the MCP server is running, flows/42.json contains a cached issue_body, and a compaction snapshot exists
    When a dev sub-agent calls get_task_context with issue_id "42"
    Then the tool returns the cached issue_body, the current flow state from flows/42.json, and the content of the most recent snapshot in compaction/

  @type:edge
  # why: TDR requires caching issue body via gh CLI when not present in flow JSON — fetch-and-cache must happen transparently
  @status:implemented
  @changed:2026-04-12
  Scenario: get_task_context fetches issue body via gh CLI when not cached
    Given the MCP server is running and flows/42.json does not have an issue_body field
    When a dev sub-agent calls get_task_context with issue_id "42"
    Then the gh CLI is called to fetch the issue body for issue 42
    And the issue_body is written to flows/42.json before returning
    And the tool returns the fetched issue_body alongside the current flow state

  @type:edge
  # why: perkins-github-operations TDR requires gh CLI failures to be logged and handled gracefully — the tool must not crash the MCP server
  @status:implemented
  @changed:2026-04-12
  Scenario: get_task_context returns partial context when gh CLI fails to fetch issue body
    Given the MCP server is running, flows/42.json has no issue_body, and the gh CLI returns a non-zero exit code
    When a dev sub-agent calls get_task_context with issue_id "42"
    Then the error is logged to recovery.log
    And the tool returns the current flow state with issue_body set to null
    And the MCP server continues running without raising an exception

  # ── MASTER ORCHESTRATOR ───────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Master Orchestrator is created with SqliteSaver and session thread_id
    Given a session_id "perk_a1b2c3" and a valid PerkinsConfig
    When the Master Orchestrator is initialized
    Then create_deep_agent() is called with a SqliteSaver checkpointer at .perkins/sessions/perk_a1b2c3/graph.db
    And the thread_id used for all invoke() calls is "perk_a1b2c3"
    And all invoke() calls pass version="v2"

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: perkins chat resumes interrupted Master with human answer
    Given the Master has an interrupt payload on the interrupt_queue for issue "42"
    When the developer runs perkins chat, views the question, and provides the answer "Use the Repository pattern"
    Then invoke is called with Command(resume={"answer": "Use the Repository pattern"}) and version="v2"
    And the answer is placed on the answer_queue for issue "42"
    And the ask_master tool handler returns the answer to the dev sub-agent

  @type:main
  @status:new
  Scenario: Context compaction triggers at threshold and stores snapshot
    Given the Master's context token usage has reached the compaction_threshold from perkins.yaml
    When the Master's compaction node runs
    Then a snapshot file is written to .perkins/sessions/{session-id}/compaction/snapshot-{timestamp}.md
    And the snapshot contains: project context, active flow states, pending escalations, recent events
    And the Master's context is rebuilt from the snapshot on the next invocation
