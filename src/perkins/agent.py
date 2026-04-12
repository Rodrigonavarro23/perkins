"""
Dev sub-agent lifecycle management for Perkins.
Governed by: docs/tdrs/perkins-subprocess-management.md, docs/tdrs/perkins-serialization.md
"""
from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from perkins.config import PerkinsConfig
from perkins.models import FlowState, FlowStatus
from perkins.session import _atomic_write


# ── Command resolution ───────────────────────────────────────────────────────

def get_agent_command(tool: str) -> list[str]:
    """Return the CLI invocation list for the given dev agent tool."""
    _commands: dict[str, list[str]] = {
        "claude-code": ["claude", "--print"],
        "gemini": ["gemini", "-p"],
        "codex": ["codex", "--full-auto"],
    }
    if tool not in _commands:
        raise ValueError(f"Unknown dev agent tool: {tool!r}")
    return _commands[tool]


# ── Worktree management ──────────────────────────────────────────────────────

def create_worktree(issue_id: str, worktrees_dir: Path) -> None:
    """
    Create an isolated git worktree for the issue at
    .worktrees/issue-{id}/ on branch perkins/issue-{id}.
    """
    branch = f"perkins/issue-{issue_id}"
    worktree_path = worktrees_dir / f"issue-{issue_id}"
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch],
        check=True,
    )


# ── Flow state transitions ───────────────────────────────────────────────────

def _flow_file(session_dir: Path, issue_id: str) -> Path:
    return session_dir / "flows" / f"{issue_id}.json"


def set_flow_in_progress(session_dir: Path, issue_id: str) -> None:
    """Transition a flow from any state to in_progress (called before subprocess start)."""
    path = _flow_file(session_dir, issue_id)
    flow = FlowState.model_validate_json(path.read_text(encoding="utf-8"))
    flow.status = FlowStatus.in_progress
    _atomic_write(path, flow.model_dump_json(indent=2))


def handle_agent_exit(
    session_dir: Path,
    issue_id: str,
    exit_code: int,
    pr_url: Optional[str] = None,
) -> None:
    """
    Transition flow state after the subprocess exits.
    exit_code 0 → completed (records pr_url if provided).
    Any other exit_code → failed (no auto-retry per TDR).
    """
    path = _flow_file(session_dir, issue_id)
    flow = FlowState.model_validate_json(path.read_text(encoding="utf-8"))
    if exit_code == 0:
        flow.status = FlowStatus.completed
        if pr_url:
            flow.pr_url = pr_url
    else:
        flow.status = FlowStatus.failed
    _atomic_write(path, flow.model_dump_json(indent=2))


# ── Log utilities ────────────────────────────────────────────────────────────

def get_last_n_lines(log_path: Path, n: int) -> list[str]:
    """Return the last n lines of agent.log (for failure reports in perkins status)."""
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8").splitlines()
    return lines[-n:] if len(lines) > n else lines


# ── Subprocess management ────────────────────────────────────────────────────

async def spawn_agent(
    issue_id: str,
    session_dir: Path,
    worktree_path: Path,
    config: PerkinsConfig,
) -> int:
    """
    Spawn the dev sub-agent subprocess in the issue's worktree.

    Steps:
      1. Mark flow as in_progress (before subprocess starts).
      2. Create log directory.
      3. Spawn subprocess via asyncio.create_subprocess_exec (stdout+stderr=PIPE).
      4. Collect output via communicate() and write to agent.log.
      5. Return the process exit code (caller decides on completed/failed transition).
    """
    log_dir = session_dir / "flows" / issue_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "agent.log"

    cmd = get_agent_command(config.dev_agents.default_tool)

    set_flow_in_progress(session_dir, issue_id)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=worktree_path,
    )

    stdout, stderr = await process.communicate()

    with open(log_path, "wb") as log_file:
        log_file.write(stdout)
        if stderr:
            log_file.write(stderr)

    return process.returncode
