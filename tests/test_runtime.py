"""
Unit tests for perkins runtime module — covers:
  - Scenario: Runtime entry point writes PID file and starts the event loop
  - Scenario: runtime_main starts stub MCP server, stub Master, and Watcher loop
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from perkins.config import PerkinsConfig
from perkins.runtime import runtime_main


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


# ── Scenario: Runtime entry point writes PID and starts event loop ────────────

def test_runtime_module_has_main_block():
    """perkins/runtime.py must be executable as -m perkins.runtime."""
    import perkins.runtime as rt
    # The module must expose runtime_main as a top-level coroutine
    assert asyncio.iscoroutinefunction(rt.runtime_main)


def test_runtime_writes_pid_file(tmp_path):
    """runtime_main writes the current process PID to runtime.pid on startup."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    pid_file = session_dir / "runtime.pid"

    async def _run():
        with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
            with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                evt = asyncio.Event()
                evt.set()
                mock_evt.return_value = evt
                # Suppress unlink so the file survives for assertion
                with patch.object(Path, "unlink"):
                    await runtime_main(session_id, config)

    asyncio.run(_run())

    assert pid_file.exists()
    assert pid_file.read_text().strip() == str(os.getpid())


def test_runtime_deletes_pid_file_on_clean_exit(tmp_path):
    """runtime_main removes runtime.pid after a clean shutdown."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    async def _run():
        with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
            with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                evt = asyncio.Event()
                evt.set()
                mock_evt.return_value = evt
                await runtime_main(session_id, config)

    asyncio.run(_run())

    pid_file = session_dir / "runtime.pid"
    assert not pid_file.exists()


# ── Scenario: runtime_main starts stub MCP server, stub Master, Watcher loop ──

def test_runtime_main_logs_mcp_stub(tmp_path, capsys):
    config = _make_config(tmp_path)
    session_id = "perk_112233"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    async def _run():
        with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
            with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                evt = asyncio.Event()
                evt.set()
                mock_evt.return_value = evt
                await runtime_main(session_id, config)

    asyncio.run(_run())

    captured = capsys.readouterr()
    assert "perkins-master MCP server started [stub]" in captured.out
    assert "7331" in captured.out


def test_runtime_main_logs_master_stub(tmp_path, capsys):
    config = _make_config(tmp_path)
    session_id = "perk_112233"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    async def _run():
        with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
            with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                evt = asyncio.Event()
                evt.set()
                mock_evt.return_value = evt
                await runtime_main(session_id, config)

    asyncio.run(_run())

    captured = capsys.readouterr()
    assert "Master Orchestrator started [stub]" in captured.out
    assert session_id in captured.out


def test_runtime_main_creates_watcher_loop_task(tmp_path):
    """runtime_main must call watcher_loop with the session_id."""
    config = _make_config(tmp_path)
    session_id = "perk_112233"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    async def _run():
        mock_watcher = AsyncMock()
        with patch("perkins.runtime.watcher_loop", mock_watcher):
            with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                evt = asyncio.Event()
                evt.set()
                mock_evt.return_value = evt
                await runtime_main(session_id, config)
        # Verify watcher_loop was invoked with the right session_id
        mock_watcher.assert_called_once_with(session_id, config)

    asyncio.run(_run())
