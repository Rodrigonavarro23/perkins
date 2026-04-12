@constraints
# governed_by:
#   - docs/tdrs/perkins-runtime-process.md
#   - docs/tdrs/perkins-cli-framework.md
#   - docs/tdrs/perkins-agent-orchestration.md
#   - docs/tdrs/perkins-mcp-server.md
#   - docs/tdrs/perkins-subprocess-management.md
#   - docs/tdrs/perkins-flow-lifecycle.md
#   - docs/tdrs/perkins-serialization.md
#   - .cliplin/knowledge/cliplin-acd-https-github.com-Rodrigonavarro23-cliplin-knowledge/tdrs/acd-agent-delivery-contract.md
#   - .cliplin/knowledge/cliplin-acd-https-github.com-Rodrigonavarro23-cliplin-knowledge/tdrs/acd-session-workflow.md
# conflicts: []
# gaps:
#   - "A stale PID file left by SIGKILL is not handled; perkins start does not clean it up (accepted as out of scope)"
# escalation_triggers:
#   - "deepagents or mcp packages become pip-installable during implementation — do not replace stubs without a new acd-spec-cycle"
#   - "The watcher_loop queue drain requires accessing active_flows_count from outside FlowDispatcher — if no clean API exists, stop and ask"
Feature: Perkins Runtime Integration
  As the Perkins background runtime,
  I want a wired asyncio event loop that connects Watcher, FlowDispatcher,
  and dev sub-agent spawning,
  So that when `perkins start` exits, issues are picked up and resolved
  autonomously without any further human interaction.

  # ── BACKGROUND PROCESS LAUNCHER ───────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: _start_background_session launches a detached runtime process
    Given a valid PerkinsConfig and a session directory created by start_session()
    When _start_background_session is called
    Then a subprocess is launched via subprocess.Popen with start_new_session=True
    And the runtime entry point is perkins.runtime invoked as a Python module
    And the function returns the session_id immediately without waiting for the process
    And the runtime PID is written to .perkins/sessions/{session-id}/runtime.pid

  @type:edge
  # why: perkins-runtime-process TDR requires stop to read PID file; if launch fails the CLI must still report the error
  @status:implemented
  @changed:2026-04-12
  Scenario: _start_background_session raises RuntimeError if Popen fails
    Given subprocess.Popen raises an OSError (e.g. Python interpreter not found)
    When _start_background_session is called
    Then a RuntimeError is raised with the underlying OSError as cause

  # ── RUNTIME ENTRY POINT ────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Runtime entry point writes PID file and starts the event loop
    Given a session_id and config_path passed as CLI arguments to perkins.runtime
    When the runtime module is executed
    Then it writes its own PID to .perkins/sessions/{session-id}/runtime.pid
    And it calls asyncio.run(runtime_main(session_id, config))
    And the PID file is deleted on clean exit

  # ── RUNTIME EVENT LOOP ─────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: runtime_main starts stub MCP server, stub Master, and Watcher loop
    Given a valid session_id and PerkinsConfig
    When runtime_main is called
    Then it logs "perkins-master MCP server started [stub] on port {port}"
    And it logs "Master Orchestrator started [stub] for session {session_id}"
    And a watcher_loop asyncio task is created and begins polling

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher loop dispatches a new issue and spawns a dev sub-agent task
    Given the runtime is running and the Watcher detects a new issue #42
    When watcher_loop calls poll_once() and the issue is not in the registry
    Then FlowDispatcher.dispatch() is called for issue #42
    And asyncio.create_task(spawn_agent(...)) is called immediately
    And the flow status for issue #42 is set to "in_progress"

  @type:complementary
  # why: completes the dispatch cycle — queued issues must be drained after each poll so they are not stranded indefinitely
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher loop drains the dispatch queue after each poll when slots are free
    Given the runtime is running with one queued issue #55 and a now-free concurrency slot
    When watcher_loop completes a poll_once() cycle
    Then issue #55 is dequeued and asyncio.create_task(spawn_agent(...)) is called for it
    And the flow status for issue #55 is updated to "in_progress"

  @type:edge
  # why: perkins-flow-lifecycle TDR defines max_concurrent; queued issues must not spawn a task when at the limit
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher loop queues an issue when concurrency limit is reached and does not spawn
    Given the runtime is running with active flows equal to dev_agents.max_concurrent
    When the Watcher dispatches a new issue #56
    Then issue #56 is added to the dispatch queue with status "queued"
    And NO asyncio.create_task(spawn_agent(...)) call is made for issue #56

  # ── GRACEFUL SHUTDOWN ──────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Runtime shuts down cleanly on SIGTERM
    Given a running runtime with an active watcher_loop task
    When the runtime process receives SIGTERM
    Then the _shutdown_event is set
    And runtime_main awaits pending spawn_agent tasks with a 5-second timeout
    And all asyncio tasks are cancelled
    And the PID file is deleted before the process exits

  # ── perkins stop — RUNTIME TERMINATION ────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: perkins stop sends SIGTERM to the runtime process via PID file
    Given a running session with a PID file at .perkins/sessions/{session-id}/runtime.pid
    When the developer runs `perkins stop {session-id}`
    Then stop_session() reads the PID from the runtime.pid file
    And sends SIGTERM to the runtime process
    And waits up to 5 seconds for the process to exit

  @type:edge
  # why: perkins-runtime-process TDR requires stop to handle missing PID gracefully; e.g. after a SIGKILL
  @status:implemented
  @changed:2026-04-12
  Scenario: perkins stop handles a missing PID file without error
    Given a session where the runtime.pid file does not exist
    When the developer runs `perkins stop {session-id}`
    Then stop_session() logs a warning about the missing PID file
    And exits without raising an exception
