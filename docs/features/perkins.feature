@constraints
# governed_by:
#   - docs/tdrs/perkins-cli-framework.md
#   - docs/tdrs/perkins-mcp-server.md
#   - docs/tdrs/perkins-agent-orchestration.md
#   - docs/tdrs/perkins-subprocess-management.md
#   - docs/tdrs/perkins-serialization.md
#   - docs/tdrs/perkins-github-operations.md
#   - docs/tdrs/perkins-flow-lifecycle.md
#   - .cliplin/knowledge/cliplin-acd-https-github.com-Rodrigonavarro23-cliplin-knowledge/tdrs/acd-agent-delivery-contract.md
#   - .cliplin/knowledge/cliplin-acd-https-github.com-Rodrigonavarro23-cliplin-knowledge/tdrs/acd-session-workflow.md
#   - .cliplin/knowledge/cliplin-acd-https-github.com-Rodrigonavarro23-cliplin-knowledge/tdrs/acd-pipeline-gates.md
# conflicts: []
# gaps: []
# escalation_triggers:
#   - "A dev sub-agent opens a PR that conflicts with another in-flight PR for the same files"
#   - "The perkins-master MCP server port is already in use on perkins start"
#   - "cliplin reindex fails during startup validation"
Feature: Perkins Autonomous Multi-Agent Development System
  As a developer with a GitHub repository configured with cliplin,
  I want to run `perkins start` and have issues resolved end-to-end by AI dev agents,
  So that I can focus on high-level decisions while Perkins handles issue resolution autonomously.

  # ── SESSION LIFECYCLE ──────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-11
  Scenario: Starting a Perkins session returns a session ID immediately
    Given a cliplin-initialized repository with a valid perkins.yaml
    And all startup validation checks pass (cliplin, gh CLI, auth, cliplin-acd)
    When the developer runs `perkins start`
    Then a session ID is printed to stdout (format: perk_[a-f0-9]{6})
    And the Master Orchestrator starts in the background
    And the Watcher daemon starts polling GitHub issues
    And the perkins-master MCP server begins listening on the configured port
    And the process exits immediately (non-blocking)

  @type:edge
  # why: perkins-serialization TDR requires validation to exit with code 1 on invalid config; invalid config is the primary startup failure mode
  @status:implemented
  @changed:2026-04-11
  Scenario: Starting with an invalid perkins.yaml exits with a validation error
    Given a repository with a perkins.yaml missing the required github_repo field
    When the developer runs `perkins start`
    Then the CLI prints a human-readable Pydantic validation error identifying the missing field
    And the process exits with code 1
    And no background processes are started

  @type:edge
  # why: perkins-serialization TDR requires exit code 1 on validation failure; out-of-range config values are a distinct failure class from missing fields
  @status:implemented
  @changed:2026-04-11
  Scenario: Starting with out-of-range perkins.yaml values exits with a validation error
    Given a repository with a perkins.yaml where dev_agents.max_concurrent is set to -1
    When the developer runs `perkins start`
    Then the CLI prints a Pydantic validation error identifying the invalid field and its constraint
    And the process exits with code 1

  @type:edge
  # why: startup validation requires checking each dependency in order; missing gh CLI is a hard early failure
  @status:implemented
  @changed:2026-04-11
  Scenario: Starting without gh CLI installed exits with an actionable error
    Given a repository where the gh CLI is not installed
    When the developer runs `perkins start`
    Then the CLI prints: "GitHub CLI is required. Install from: https://cli.github.com"
    And the process exits with code 1

  @type:main
  @status:implemented
  @changed:2026-04-11
  Scenario: Stopping a running session gracefully persists all flow states
    Given a running Perkins session with ID "perk_a3f9c2" and 2 active flows
    When the developer runs `perkins stop perk_a3f9c2`
    Then all active flows are persisted to their respective flow JSON files
    And the Master Orchestrator shuts down cleanly
    And the Watcher daemon stops polling
    And the perkins-master MCP server stops accepting connections

  # ── ISSUE WATCHING AND DISPATCH ────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher detects a new GitHub issue and dispatches it to the Master
    Given a running Perkins session
    And a new GitHub issue #42 titled "Implement refund endpoint" is created in the repository
    When the Watcher polls GitHub issues on its next interval
    Then the Watcher dispatches issue #42 to the Master Orchestrator
    And a new flow entry is created at .perkins/sessions/{session-id}/flows/42.json
    And the flow status is set to "dispatched"
    And the issue is added to the active flow registry to prevent duplicate processing

  @type:edge
  # why: duplicate prevention is an explicit responsibility of the Watcher per the intent; without it the Master would spawn two dev agents for the same issue
  @status:implemented
  @changed:2026-04-11
  Scenario: Watcher skips an issue already in the active flow registry
    Given a running Perkins session with issue #42 already in the active flow registry
    When the Watcher polls GitHub and issue #42 appears in the results again
    Then the Watcher does NOT dispatch issue #42 to the Master
    And no new flow entry is created for issue #42
    And the existing flow for issue #42 is unchanged

  @type:edge
  # why: perkins-github-operations TDR requires watcher to continue polling on gh CLI failure; crashing would halt all issue processing
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher continues polling when gh CLI returns a non-zero exit
    Given a running Perkins session
    When the Watcher polls GitHub and the gh CLI returns exit code 1 with a network error
    Then the error is logged to the session recovery log
    And the Watcher waits for the next poll interval
    And the Watcher does NOT crash or stop the session

  # ── DEV SUB-AGENT LIFECYCLE ────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Master spawns a dev sub-agent for a dispatched issue
    Given a running Perkins session
    And issue #42 has been dispatched to the Master
    And the number of active flows is below dev_agents.max_concurrent in perkins.yaml
    And dev_agents.default_tool is set to "claude-code" in perkins.yaml
    When the Master creates the worktree and spawns the dev sub-agent
    Then a git worktree is created at .worktrees/issue-42/ on branch perkins/issue-42
    And the dev sub-agent process is started via asyncio.create_subprocess_exec with flag "--print"
    And raw output is streamed to .perkins/sessions/{session-id}/flows/42/agent.log
    And the flow status is updated to "in_progress"

  @type:edge
  # why: perkins-flow-lifecycle TDR defines max_concurrent; dispatched issues must queue rather than spawn when the limit is reached
  @status:implemented
  @changed:2026-04-12
  Scenario: Master queues a dispatched issue when the concurrency limit is reached
    Given a running Perkins session where active flows equal dev_agents.max_concurrent
    When a new issue #55 is dispatched to the Master
    Then no worktree or subprocess is created for issue #55
    And issue #55 is added to the in-memory dispatch queue
    And the flow status for issue #55 is set to "queued"

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Dev sub-agent completes successfully and opens a PR
    Given a dev sub-agent running for issue #42
    When the dev sub-agent exits with code 0 and a PR has been opened on branch perkins/issue-42
    Then the flow status is updated to "completed"
    And the flow JSON records the PR URL
    And the flow JSON is written atomically (tmp file then rename)

  @type:edge
  # why: perkins-subprocess-management TDR prohibits automatic retry on non-zero exit; human decision is required
  @status:implemented
  @changed:2026-04-12
  Scenario: Dev sub-agent exits with non-zero code and awaits human decision
    Given a dev sub-agent running for issue #42
    When the dev sub-agent process exits with a non-zero exit code
    Then the flow status is updated to "failed"
    And the Master reports the failure via `perkins status` including the last 20 lines of agent.log
    And no automatic retry is attempted

  # ── HUMAN ESCALATION (ask_master) ──────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Master answers a dev sub-agent question from loaded context
    Given a dev sub-agent working on issue #38
    When the dev sub-agent calls ask_master with a question answerable from the Master's loaded cliplin context
    Then the Master responds to the dev sub-agent immediately without escalating to the human
    And the flow continues without interruption

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Master escalates an unanswerable question to the human via the issue thread
    Given a dev sub-agent working on issue #38
    When the dev sub-agent calls ask_master with a question the Master cannot answer from context
    Then the Master sets the flow status to "waiting_human"
    And the Master spawns an Answer Agent for issue #38
    And the Answer Agent posts the question to the GitHub issue thread using gh issue comment
    And the Master graph enters interrupt state awaiting human response

  @type:complementary
  # why: completes the escalation cycle — without the resume path the interrupt would block indefinitely
  @status:implemented
  @changed:2026-04-12
  Scenario: Human responds on the issue thread and Master resumes the dev sub-agent
    Given flow #38 is in "waiting_human" state with a question posted on the issue thread
    When the Answer Agent detects a human response on the issue thread
    Then the Answer Agent delivers the response to the Master
    And the Master resumes via Command(resume={"answer": <human_response>})
    And the Master responds to the dev sub-agent's pending ask_master call
    And the flow status is updated back to "in_progress"

  # ── CRASH RECOVERY ─────────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: Perkins recovers after a crash and restores session state
    Given a previous session "perk_a3f9c2" was interrupted with:
      | issue | status         |
      | #42   | in_progress    |
      | #38   | waiting_human  |
      | #35   | completed      |
    When the developer runs `perkins start`
    Then Perkins detects the incomplete session in .perkins/sessions/
    And the flow for issue #42 is set to "failed" (in_progress at crash → failed on recovery)
    And the Master resumes the flow for issue #38 from its LangGraph checkpoint
    And an Answer Agent is re-spawned for issue #38
    And the flow for issue #35 remains "completed" and is not touched
    And recovery actions are logged to .perkins/sessions/perk_a3f9c2/recovery.log

  # ── WORKTREE CLEANUP ───────────────────────────────────────────────────────

  @type:complementary
  # why: perkins-flow-lifecycle TDR requires human confirmation before worktree deletion when cleanup_worktree_on is issue_closed
  @status:implemented
  @changed:2026-04-12
  Scenario: Watcher detects closed issue and prompts human before deleting worktree
    Given cleanup_worktree_on is set to "issue_closed" in perkins.yaml
    And a completed flow for issue #42 with a worktree at .worktrees/issue-42/
    When the Watcher detects that GitHub issue #42 has transitioned to "closed" state
    Then the Master prompts: "Issue #42 is closed. Delete worktree at .worktrees/issue-42/? [y/N]"
    And if the human confirms, the worktree is removed using git worktree remove --force
    And if the human declines, the worktree is left in place and no further prompts are sent

  # ── PERKINS SUMMARY ────────────────────────────────────────────────────────

  @type:main
  @status:implemented
  @changed:2026-04-12
  Scenario: perkins summary produces a human-readable project context snapshot
    Given a cliplin-initialized repository with features, TDRs, and ADRs indexed in the context store
    When the developer runs `perkins summary`
    Then the output includes the repository name and description from perkins.yaml
    And the output includes the inferred technology stack derived from the codebase
    And the output includes key architectural responsibilities loaded from the cliplin context store
    And the output includes key points from ADRs and TDRs that explain how the project works

  @type:complementary
  # why: --json is the machine-readable contract for federated orchestration described in the intent doc
  @status:implemented
  @changed:2026-04-12
  Scenario: perkins summary --json produces a stable machine-readable project description
    Given a cliplin-initialized repository with context indexed in the cliplin context store
    When the developer runs `perkins summary --json`
    Then the output is valid JSON
    And the JSON contains top-level keys: repo, stack, responsibilities, key_decisions
    And each key_decision entry references its source ADR or TDR file path
    And the JSON can be parsed by an external orchestrator to understand the project without inspecting its internals
