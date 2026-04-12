---
tdr: "1.0"
id: "perkins-subprocess-management"
title: "Dev Sub-Agent Subprocess Management"
summary: "Dev sub-agents (Claude Code, Gemini CLI, Codex CLI) are managed as asyncio subprocesses."
---

# rules

## Subprocess creation

- Dev sub-agents MUST be spawned using `asyncio.create_subprocess_exec()` with `stdout=asyncio.subprocess.PIPE` and `stderr=asyncio.subprocess.PIPE`.
- The working directory for each subprocess MUST be the issue's isolated git worktree path (`.worktrees/issue-{id}/`).
- Supported backends and their flags:
  - Claude Code: `claude --print`
  - Gemini CLI: `gemini -p`
  - Codex CLI: `codex --full-auto`

## Output handling

- Raw stdout and stderr from dev sub-agents are streamed line-by-line and written to `.perkins/sessions/{session-id}/flows/{issue-id}/agent.log`.
- Raw stdout/stderr is NOT injected into the Master's context window.
- All structured communication from dev sub-agents to the Master MUST go through the `perkins-master` MCP server tools (`ask_master`, `report_progress`, `get_task_context`).

## Lifecycle

- Each dev sub-agent runs in its own isolated git worktree on branch `perkins/issue-{id}`.
- The subprocess is considered complete when it exits with code 0 and has opened a PR.
- On non-zero exit, the Master reports the failure to the human via the CLI chat interface.
- The Master MUST NOT retry a failed subprocess automatically — human decision required.

## Crash recovery

- On session recovery, flows that were in `in_progress` state at crash time MUST be set to `failed`.
- The Master reports each recovered `failed` flow to the human on the next `perkins chat` or `perkins status` call.
- The human decides whether to re-launch the dev sub-agent for each failed flow; the Master MUST NOT re-spawn automatically during recovery.
