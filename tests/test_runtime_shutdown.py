"""
Unit tests for perkins runtime shutdown and perkins stop PID termination — covers:
  - Scenario: Runtime shuts down cleanly on SIGTERM
  - Scenario: perkins stop sends SIGTERM to the runtime process via PID file
  - Scenario: perkins stop handles a missing PID file without error
"""
from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from perkins.config import PerkinsConfig
from perkins.runtime import runtime_main
from perkins.session import stop_session


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


# ── Scenario: Runtime shuts down cleanly on SIGTERM ──────────────────────────

def test_runtime_sets_shutdown_event_on_sigterm(tmp_path):
    """SIGTERM must set the shutdown event so runtime_main exits its wait loop."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    shutdown_was_set = []

    async def _run():
        mock_master = MagicMock()
        mock_master.start.return_value = asyncio.ensure_future(asyncio.sleep(0))
        with patch("perkins.runtime.MasterOrchestrator", return_value=mock_master):
            with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
                with patch("perkins.runtime._get_shutdown_event") as mock_get_evt:
                    evt = asyncio.Event()
                    mock_get_evt.return_value = evt

                    # Send SIGTERM to ourselves after a short delay
                    async def _send_sigterm():
                        await asyncio.sleep(0.05)
                        os.kill(os.getpid(), signal.SIGTERM)

                    asyncio.create_task(_send_sigterm())
                    await runtime_main(session_id, config)
                    shutdown_was_set.append(evt.is_set())

    asyncio.run(_run())
    assert shutdown_was_set == [True]


def test_runtime_cancels_watcher_task_on_shutdown(tmp_path):
    """runtime_main cancels the watcher_loop task during shutdown."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    cancelled_tasks = []

    async def _slow_watcher(sid, cfg, **kwargs):
        try:
            await asyncio.sleep(999)
        except asyncio.CancelledError:
            cancelled_tasks.append(sid)
            raise

    async def _run():
        mock_master = MagicMock()
        mock_master.start.return_value = asyncio.ensure_future(asyncio.sleep(0))
        with patch("perkins.runtime.MasterOrchestrator", return_value=mock_master):
            with patch("perkins.runtime.watcher_loop", side_effect=_slow_watcher):
                with patch("perkins.runtime._get_shutdown_event") as mock_get_evt:
                    evt = asyncio.Event()
                    mock_get_evt.return_value = evt

                    async def _trigger_shutdown():
                        await asyncio.sleep(0.05)
                        evt.set()

                    asyncio.create_task(_trigger_shutdown())
                    await runtime_main(session_id, config)

    asyncio.run(_run())
    assert cancelled_tasks == [session_id]


def test_runtime_deletes_pid_file_after_sigterm(tmp_path):
    """PID file is removed after graceful shutdown."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    async def _run():
        mock_master = MagicMock()
        mock_master.start.return_value = asyncio.ensure_future(asyncio.sleep(0))
        with patch("perkins.runtime.MasterOrchestrator", return_value=mock_master):
            with patch("perkins.runtime.watcher_loop", new=AsyncMock()):
                with patch("perkins.runtime._get_shutdown_event") as mock_get_evt:
                    evt = asyncio.Event()
                    mock_get_evt.return_value = evt

                    async def _trigger():
                        await asyncio.sleep(0.05)
                        evt.set()

                    asyncio.create_task(_trigger())
                    await runtime_main(session_id, config)

    asyncio.run(_run())
    assert not (session_dir / "runtime.pid").exists()


# ── Scenario: perkins stop sends SIGTERM to the runtime process via PID file ─

def test_stop_session_sends_sigterm_via_pid_file(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_112233"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    (session_dir / "flows").mkdir(parents=True)

    # Write a fake session.json so stop_session can update it
    from perkins.models import SessionState
    (session_dir / "session.json").write_text(
        SessionState(session_id=session_id).model_dump_json(), encoding="utf-8"
    )

    # Write a PID file with a fake PID
    fake_pid = 99999
    (session_dir / "runtime.pid").write_text(str(fake_pid), encoding="utf-8")

    with patch("perkins.session.os.kill") as mock_kill:
        with patch("perkins.session.os.waitpid", return_value=(fake_pid, 0)):
            stop_session(session_id, config)

    mock_kill.assert_called_once_with(fake_pid, signal.SIGTERM)


def test_stop_session_waits_for_process_after_sigterm(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_112233"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    (session_dir / "flows").mkdir(parents=True)

    from perkins.models import SessionState
    (session_dir / "session.json").write_text(
        SessionState(session_id=session_id).model_dump_json(), encoding="utf-8"
    )
    (session_dir / "runtime.pid").write_text("99999", encoding="utf-8")

    waitpid_calls = []

    def _fake_waitpid(pid, options):
        waitpid_calls.append(pid)
        return (pid, 0)

    with patch("perkins.session.os.kill"):
        with patch("perkins.session.os.waitpid", side_effect=_fake_waitpid):
            stop_session(session_id, config)

    assert 99999 in waitpid_calls


# ── Scenario: perkins stop handles a missing PID file without error ───────────

def test_stop_session_handles_missing_pid_file_without_error(tmp_path, caplog):
    config = _make_config(tmp_path)
    session_id = "perk_445566"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    (session_dir / "flows").mkdir(parents=True)

    from perkins.models import SessionState
    (session_dir / "session.json").write_text(
        SessionState(session_id=session_id).model_dump_json(), encoding="utf-8"
    )
    # No runtime.pid file written

    import logging
    with caplog.at_level(logging.WARNING, logger="perkins.session"):
        stop_session(session_id, config)  # must not raise

    assert any("runtime.pid" in r.message or "pid" in r.message.lower()
               for r in caplog.records)


def test_stop_session_does_not_call_kill_when_pid_file_missing(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_445566"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    (session_dir / "flows").mkdir(parents=True)

    from perkins.models import SessionState
    (session_dir / "session.json").write_text(
        SessionState(session_id=session_id).model_dump_json(), encoding="utf-8"
    )

    with patch("perkins.session.os.kill") as mock_kill:
        stop_session(session_id, config)

    mock_kill.assert_not_called()
