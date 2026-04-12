"""
Perkins asyncio runtime entry point.
Governed by: docs/tdrs/perkins-runtime-process.md, docs/tdrs/perkins-cli-framework.md
"""
from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

import yaml

from perkins.agent import handle_agent_exit, spawn_agent
from perkins.config import PerkinsConfig


# ── Shutdown event ────────────────────────────────────────────────────────────

_shutdown_event: asyncio.Event | None = None


def _get_shutdown_event() -> asyncio.Event:
    """Return the module-level shutdown event (created lazily per event loop)."""
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    return _shutdown_event


def _handle_signal(signum: int, frame: object) -> None:
    """Signal handler: set the shutdown event to begin graceful shutdown."""
    loop = asyncio.get_event_loop()
    loop.call_soon_threadsafe(_get_shutdown_event().set)


# ── Stub components ───────────────────────────────────────────────────────────

async def watcher_loop(
    session_id: str,
    config: PerkinsConfig,
    *,
    _watcher=None,
    _dispatch_queue=None,
    _initial_active_flows: int = 0,
) -> None:
    """
    Watcher polling loop — connects Watcher, FlowDispatcher, and spawn_agent.
    On each iteration:
      1. Calls watcher.poll_once() → returns dispatched FlowStates.
      2. Spawns an asyncio task for each dispatched issue.
      3. Drains the DispatchQueue for any queued issues that fit within max_concurrent.

    Parameters prefixed with _ are for test injection only.
    """
    from perkins.dispatcher import DispatchQueue, FlowDispatcher
    from perkins.watcher import IssueRegistry, Watcher

    state_dir = Path(config.session.state_dir)
    session_dir = state_dir / "sessions" / session_id
    worktrees_dir = Path(".worktrees")

    if _watcher is None:
        registry = IssueRegistry()
        queue: DispatchQueue = _dispatch_queue if _dispatch_queue is not None else DispatchQueue()
        dispatcher = FlowDispatcher(registry, queue, config.dev_agents.max_concurrent)
        watcher = Watcher(registry, dispatcher, session_dir, config.repo.github_repo)
    else:
        watcher = _watcher
        queue = _dispatch_queue if _dispatch_queue is not None else DispatchQueue()

    active = [_initial_active_flows]
    shutdown = _get_shutdown_event()

    def _make_done_callback(issue_id: str):
        def _on_done(task: asyncio.Task) -> None:
            active[0] -= 1
            if not task.cancelled():
                try:
                    exit_code = task.result()
                    handle_agent_exit(session_dir, issue_id, exit_code or 0)
                except Exception:
                    handle_agent_exit(session_dir, issue_id, 1)
        return _on_done

    while not shutdown.is_set():
        dispatched_flows = watcher.poll_once(active[0])

        for flow in dispatched_flows:
            worktree_path = worktrees_dir / f"issue-{flow.issue_id}"
            active[0] += 1
            task = asyncio.create_task(
                spawn_agent(flow.issue_id, session_dir, worktree_path, config)
            )
            task.add_done_callback(_make_done_callback(flow.issue_id))

        # Drain queued issues into available concurrency slots
        while queue.size() > 0 and active[0] < config.dev_agents.max_concurrent:
            issue_id = queue.dequeue()
            if issue_id is None:
                break
            worktree_path = worktrees_dir / f"issue-{issue_id}"
            active[0] += 1
            task = asyncio.create_task(
                spawn_agent(issue_id, session_dir, worktree_path, config)
            )
            task.add_done_callback(_make_done_callback(issue_id))

        await asyncio.sleep(config.watcher.poll_interval_seconds)


# ── Runtime main ──────────────────────────────────────────────────────────────

async def runtime_main(session_id: str, config: PerkinsConfig) -> None:
    """
    Top-level runtime coroutine. Starts stub MCP server, stub Master Orchestrator,
    and the Watcher loop. Awaits shutdown then cancels all tasks.
    """
    state_dir = Path(config.session.state_dir)
    session_dir = state_dir / "sessions" / session_id
    pid_file = session_dir / "runtime.pid"

    # Write PID
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    # Register signal handlers
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Stub: MCP server
    print(f"perkins-master MCP server started [stub] on port {config.mcp_server.port}", flush=True)

    # Stub: Master Orchestrator
    print(f"Master Orchestrator started [stub] for session {session_id}", flush=True)

    # Start Watcher loop
    watcher_task = asyncio.create_task(watcher_loop(session_id, config))

    # Await shutdown
    shutdown = _get_shutdown_event()
    await shutdown.wait()

    # Cancel all tasks with a timeout
    watcher_task.cancel()
    try:
        await asyncio.wait_for(asyncio.shield(watcher_task), timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    # Delete PID file on clean exit
    pid_file.unlink(missing_ok=True)

    # Reset shutdown event for potential re-use in tests
    global _shutdown_event
    _shutdown_event = None


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python -m perkins.runtime <session_id> <config_path>", file=sys.stderr)
        sys.exit(1)

    _session_id = sys.argv[1]
    _config_path = Path(sys.argv[2])

    with open(_config_path) as f:
        _data = yaml.safe_load(f)
    _config = PerkinsConfig.model_validate(_data)

    asyncio.run(runtime_main(_session_id, _config))
