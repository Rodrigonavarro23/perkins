@constraints
# governed_by:
#   - docs/tdrs/perkins-chat-server.md
#   - docs/tdrs/perkins-cli-framework.md
#   - docs/tdrs/perkins-runtime-process.md
# conflicts: []
# gaps:
#   - "Chat server startup must be wired into runtime_main() in runtime.py alongside MCP server and Master Orchestrator stubs"
#   - "GET /interrupts peeks without dequeuing — concurrent perkins chat invocations would see the same question; accepted as known limitation for single-developer use"
#   - "aiohttp is not yet in project dependencies; must be added to pyproject.toml in the implementation PR"
#   - "Order of presentation when multiple interrupts are pending: FIFO by issue_id insertion order"
# escalation_triggers: []
Feature: Perkins Chat
  As a developer whose Perkins session has escalated a question,
  I want to run `perkins chat <session_id>` to see pending questions
  from the Master Orchestrator and provide answers interactively,
  so that blocked flows can resume without requiring me to monitor
  GitHub issue threads.

  # ── Happy path ──────────────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat shows pending question and delivers answer to runtime
    Given a session "perk_abc123" is running with one pending interrupt
      for issue "42" with question "Which pattern to use?"
    When the developer runs perkins chat perk_abc123
    And types "Use the Repository pattern" at the interactive prompt
    Then the CLI prints the question "Which pattern to use?"
    And the answer "Use the Repository pattern" is POSTed to
      /sessions/perk_abc123/answers/42
    And the CLI prints a confirmation that the answer was delivered
    And the CLI exits 0

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat exits cleanly when no questions are pending
    Given a session "perk_abc123" is running with no pending interrupts
    When the developer runs perkins chat perk_abc123
    Then the CLI prints "No pending questions for session perk_abc123."
    And the CLI exits 0

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat --watch polls until a question appears then prompts
    Given a session "perk_abc123" is running with no pending interrupts initially
    And a question for issue "42" arrives after 2 polling cycles
    When the developer runs perkins chat perk_abc123 --watch
    Then the CLI polls GET /interrupts every 2 seconds
    And once the question is available the CLI prints it and prompts for an answer

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat prompts for each pending question when multiple are pending
    Given a session "perk_abc123" has pending interrupts for issues "42" and "99"
    When the developer runs perkins chat perk_abc123
    Then the CLI presents both questions in FIFO order
    And delivers each answer to its respective /sessions/perk_abc123/answers/{issue_id} endpoint

  # ── Error paths ─────────────────────────────────────────────────────────────

  @type:edge
  # why: chat.port missing means runtime has not started — must not hang or give cryptic error
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat exits with error when runtime has not started
    Given no chat.port file exists for session "perk_abc123"
    When the developer runs perkins chat perk_abc123
    Then the CLI prints "Runtime not running for session perk_abc123."
    And the CLI exits 1

  @type:edge
  # why: runtime may have crashed mid-session; connection refused must give actionable signal
  @status:implemented
  @changed:2026-04-12
  Scenario: Chat exits with error when connection to runtime is refused
    Given chat.port exists for session "perk_abc123" but the runtime process is down
    When the developer runs perkins chat perk_abc123
    Then the CLI prints "Could not connect to runtime for session perk_abc123."
    And the CLI exits 1
