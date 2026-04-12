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

async def watcher_loop(session_id: str, config: PerkinsConfig) -> None:
    """
    Watcher polling loop — connects Watcher, FlowDispatcher, and spawn_agent.
    Implemented in Session 3.
    """
    shutdown = _get_shutdown_event()
    while not shutdown.is_set():
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
