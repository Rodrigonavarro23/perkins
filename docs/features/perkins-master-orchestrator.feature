@constraints
# governed_by:
#   - docs/tdrs/perkins-mcp-server.md
#   - docs/tdrs/perkins-agent-orchestration.md
#   - docs/tdrs/perkins-runtime-process.md
#   - docs/tdrs/perkins-serialization.md
#   - docs/tdrs/perkins-flow-lifecycle.md
#   - docs/tdrs/perkins-github-operations.md
#   - docs/tdrs/perkins-search.md
# conflicts: []
# gaps:
#   - "Answer Agents (deepagents subagents for posting/polling GitHub issues) are out of scope — covered by a separate feature"
# escalation_triggers:
#   - "deepagents create_deep_agent() API signature differs from what the TDR assumes at implementation time — stop and verify before wiring"
#   - "mcp SDK server startup API differs from expected usage — stop and verify the correct asyncio integration pattern"
#   - "create_deep_agent() mcp_servers parameter API differs from expected usage — stop and verify before wiring"
#   - "deepagents system prompt parameter name differs from expected — stop and verify the correct kwarg before wiring"
#   - "httpx is not available in the project dependencies at implementation time — stop and add it before wiring the search tier"
#   - "Brave or Serper API response schema differs from what perkins-search.md assumes — stop and verify result extraction keys before wiring"
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

  # ── CLIPLIN ENVIRONMENT INHERITANCE ──────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-19
  Scenario: Master loads .mcp.json and passes cliplin-context MCP as mcp_servers
    Given a project root with a valid .mcp.json containing a cliplin-context MCP server entry
    And a valid PerkinsConfig with dev_agents.default_tool "claude-code"
    When the Master Orchestrator is initialized
    Then .mcp.json is read from the project root
    And create_deep_agent() is called with mcp_servers containing the cliplin-context MCP server config
    And the Master can invoke context_query_documents during graph execution

  @type:main
  @status:implemented
  @changed:2026-04-19
  Scenario: Master loads claude-code rules from .claude/rules/ into system prompt
    Given a project root with .claude/rules/ containing context.md, context-protocol-loading.md,
      feature-first-flow.md, and feature-processing.md
    And perkins.yaml has dev_agents.default_tool set to "claude-code"
    When the Master Orchestrator is initialized
    Then all *.md files in .claude/rules/ are read and concatenated
    And create_deep_agent() is called with the concatenated rules as the system prompt prefix

  @type:main
  @status:implemented
  @changed:2026-04-19
  Scenario: Master loads gemini rules from .gemini/ into system prompt
    Given a project root with .gemini/ containing one or more *.md rule files
    And perkins.yaml has dev_agents.default_tool set to "gemini"
    When the Master Orchestrator is initialized
    Then all *.md files in .gemini/ are read and concatenated
    And create_deep_agent() is called with the concatenated rules as the system prompt prefix

  @type:main
  @status:implemented
  @changed:2026-04-19
  Scenario: Master loads cursor rules from .cursor/rules/ into system prompt
    Given a project root with .cursor/rules/ containing one or more *.mdc rule files
    And perkins.yaml has dev_agents.default_tool set to "cursor"
    When the Master Orchestrator is initialized
    Then all *.mdc files in .cursor/rules/ are read and concatenated
    And create_deep_agent() is called with the concatenated rules as the system prompt prefix

  @type:edge
  # why: cursor has a legacy single-file format; TDR requires fallback to .cursorrules when .cursor/rules/ is absent
  @status:implemented
  @changed:2026-04-19
  Scenario: Master falls back to .cursorrules when .cursor/rules/ is absent
    Given a project root with no .cursor/rules/ directory but a .cursorrules file present
    And perkins.yaml has dev_agents.default_tool set to "cursor"
    When the Master Orchestrator is initialized
    Then the content of .cursorrules is read
    And create_deep_agent() is called with that content as the system prompt prefix

  @type:main
  @status:implemented
  @changed:2026-04-19
  Scenario: Master queries cliplin context before deciding to interrupt on ask_master
    Given the Master is initialized with cliplin-context MCP tools
    And a dev sub-agent calls ask_master with issue_id "42"
      and question "Which error handling pattern does this repo use?"
    When the Master processes the ask_master call
    Then the Master calls context_query_documents on "technical-decision-records"
      with the question verbatim as query_text
    And if a relevant result is found, the Master returns the answer directly
      without triggering interrupt()
    And if no result is found in technical-decision-records, the Master queries
      the "features" collection before deciding to interrupt

  @type:edge
  # why: .mcp.json absent means no cliplin tools — Master must degrade gracefully per TDR rule
  @status:implemented
  @changed:2026-04-19
  Scenario: Master falls back to interrupt-only mode when .mcp.json is absent
    Given a project root with no .mcp.json file
    When the Master Orchestrator is initialized
    Then initialization succeeds without raising an exception
    And a warning is logged: "cliplin-context MCP unavailable — Master will escalate all unknown questions to human"
    And ask_master calls always trigger interrupt() when no MCP tools are available

  @type:edge
  # why: rules dir absent means no system prompt rules — Master must degrade gracefully per TDR rule
  @status:implemented
  @changed:2026-04-19
  Scenario: Master initializes without rules when AI tool rules directory is absent
    Given a project root with no .claude/rules/ directory
    And perkins.yaml has dev_agents.default_tool set to "claude-code"
    When the Master Orchestrator is initialized
    Then initialization succeeds without raising an exception
    And a warning is logged indicating the rules directory was not found
    And create_deep_agent() is called without a system prompt prefix

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

  # ── WEB SEARCH RESOLUTION TIER ───────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-27
  Scenario: Master resolves ask_master via web search when cliplin context is insufficient
    Given search.enabled is true in perkins.yaml with provider "brave"
    And a dev sub-agent calls ask_master with a question the Master cannot answer from cliplin context
    And the Master graph raises __interrupt__ on the first invocation
    When the Master performs a web search using the question as query
    And the search returns at least one result
    And the Master graph is invoked again with the search results appended to the context
    And the graph produces a non-interrupt answer on the second invocation
    Then the Master returns the answer directly to the dev sub-agent
    And no interrupt payload is placed on the interrupt_queue
    And the human is not notified

  @type:main
  @status:implemented
  @changed:2026-04-28
  Scenario: Master escalates to human with search context when web search does not resolve the question
    Given search.enabled is true in perkins.yaml
    And a dev sub-agent calls ask_master with a question the Master cannot answer
    And the Master graph raises __interrupt__ on both the initial and post-search invocations
    When the Master performs a web search and receives results
    And the graph still raises __interrupt__ after the second invocation with search results
    Then the interrupt payload placed on interrupt_queue includes web_search_results
      with the normalized results as a list of {title, url, snippet} objects
    And the human sees the search results alongside the question in perkins chat

  @type:edge
  # why: perkins-search TDR requires graceful fallback on any httpx error — search failure must not block the escalation path
  @status:implemented
  @changed:2026-04-27
  Scenario: Master falls back to direct human escalation when web search API call fails
    Given search.enabled is true in perkins.yaml
    And a dev sub-agent calls ask_master with a question the Master cannot answer
    And the Master graph raises __interrupt__ on the first invocation
    When the web search API call raises an httpx.HTTPStatusError or httpx.TimeoutException
    Then the error is logged as a warning
    And the Master proceeds to human escalation without web_search_results
    And the interrupt payload has web_search_results set to null
    And the MCP server continues running without raising an exception

  @type:edge
  # why: perkins-search TDR requires skipping search when api_key_env is unset — prevents silent auth failures
  @status:implemented
  @changed:2026-04-28
  Scenario: Master skips web search and escalates directly when search API key is not configured
    Given search.enabled is true in perkins.yaml
    And the environment variable named in search.api_key_env is unset or empty
    And a dev sub-agent calls ask_master with a question the Master cannot answer
    When the Master processes the ask_master call
    Then a warning is logged: "search.api_key_env is unset — skipping web search tier"
    And the Master proceeds directly to human escalation
    And web_search_results in the interrupt payload is null

  @type:complementary
  # why: search.enabled=false is the default — existing interrupt behavior must be provably unaffected when search is off
  @status:implemented
  @changed:2026-04-27
  Scenario: Master behavior is unchanged when search.enabled is false
    Given search.enabled is false or absent in perkins.yaml
    And a dev sub-agent calls ask_master with a question the Master cannot answer from context
    And the Master graph raises __interrupt__
    Then the interrupt payload is placed on interrupt_queue immediately
    And no web search is performed
    And web_search_results in the interrupt payload is null

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Context compaction triggers at threshold and stores snapshot
    Given the Master's context token usage has reached the compaction_threshold from perkins.yaml
    When the Master's compaction node runs
    Then a snapshot file is written to .perkins/sessions/{session-id}/compaction/snapshot-{timestamp}.md
    And the snapshot contains: project context, active flow states, pending escalations, recent events
    And the Master's context is rebuilt from the snapshot on the next invocation
