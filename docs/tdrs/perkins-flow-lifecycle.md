---
tdr: "1.0"
id: "perkins-flow-lifecycle"
title: "Perkins Flow Lifecycle: Concurrency, Session IDs, and Worktree Cleanup"
summary: "Rules for flow concurrency limits, session ID generation, and worktree cleanup policy."
---

# rules

## Concurrency

- The maximum number of simultaneously active dev sub-agents is controlled by
  `dev_agents.max_concurrent` in `perkins.yaml` (default: `5`).
- When the limit is reached, new dispatched issues are queued in memory by the Master.
- The Master spawns the next queued flow as soon as a running flow reaches
  `completed` or `failed` state.
- The queue is not persisted; on crash recovery, unstarted queued issues are
  re-dispatched from the Watcher's next poll.

## Session ID generation

- Session IDs MUST be generated as `"perk_" + secrets.token_hex(3)` (6 hex characters).
- `secrets.token_hex` from the Python stdlib is the only permitted source of randomness
  for session ID generation.
- Session IDs are unique within a `.perkins/sessions/` directory; on collision (extremely
  unlikely), regenerate once before raising an error.

## Worktree cleanup

- The worktree cleanup trigger is controlled by `dev_agents.cleanup_worktree_on` in
  `perkins.yaml`. Valid values:
  - `issue_closed` (default): delete `.worktrees/issue-{id}/` when the GitHub issue
    transitions to `closed` state, as detected by the Watcher's poll loop.
  - `session_stop`: delete all worktrees for the session when `perkins stop` is called.
  - `manual`: never delete automatically; the developer is responsible for cleanup.
- When `issue_closed` is the trigger and the Watcher detects the issue closed,
  the Master MUST ask the human for confirmation before deleting the worktree:
  prompt format: `"Issue #{id} is closed. Delete worktree at .worktrees/issue-{id}/? [y/N]"`
- Worktree deletion MUST use `git worktree remove --force` to ensure git index consistency.
- If worktree deletion fails for any reason, log the error and continue — do NOT
  block the session.
