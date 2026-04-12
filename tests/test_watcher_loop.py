"""
Unit tests for watcher_loop in perkins.runtime — covers:
  - Scenario: Watcher loop dispatches a new issue and spawns a dev sub-agent task
  - Scenario: Watcher loop drains the dispatch queue after each poll when slots are free
  - Scenario: Watcher loop queues an issue when concurrency limit is reached and does not spawn
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from perkins.config import PerkinsConfig
from perkins.dispatcher import DispatchQueue
from perkins.models import FlowState, FlowStatus
from perkins.runtime import watcher_loop


def _make_config(tmp_path: Path, max_concurrent: int = 5) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "dev_agents": {"max_concurrent": max_concurrent},
        "watcher": {"poll_interval_seconds": 1},
    })


def _setup_session(tmp_path: Path, session_id: str) -> Path:
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    (session_dir / "flows").mkdir(parents=True)
    return session_dir


def _run_loop_once(session_id, config, *, mock_watcher, queue=None,
                   initial_active_flows=0, spawn_mock=None):
    """Run watcher_loop for a single poll iteration then shut it down."""
    evt = asyncio.Event()
    spawned: list[str] = []

    async def fake_sleep(_):
        # Stop the loop after the first poll completes.
        # spawn_agent is called synchronously when passed to create_task,
        # so call_count is already correct before tasks execute.
        evt.set()

    if spawn_mock is None:
        spawn_mock = AsyncMock(return_value=0)

    async def _run():
        with patch("perkins.runtime.spawn_agent", spawn_mock):
            with patch("perkins.runtime.handle_agent_exit"):
                with patch("asyncio.sleep", fake_sleep):
                    with patch("perkins.runtime._get_shutdown_event", return_value=evt):
                        await watcher_loop(
                            session_id,
                            config,
                            _watcher=mock_watcher,
                            _dispatch_queue=queue,
                            _initial_active_flows=initial_active_flows,
                        )

    asyncio.run(_run())
    return spawn_mock


# ── Scenario: Watcher loop dispatches a new issue and spawns a dev sub-agent task ─

def test_watcher_loop_calls_spawn_agent_for_dispatched_issue(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_aa1122"
    _setup_session(tmp_path, session_id)

    flow_42 = FlowState(issue_id="42", status=FlowStatus.dispatched)
    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = [flow_42]

    spawn_mock = _run_loop_once(session_id, config, mock_watcher=mock_watcher)

    spawn_mock.assert_called_once_with("42", ANY, ANY, config)


def test_watcher_loop_spawn_agent_called_with_correct_issue_id(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_aa1122"
    _setup_session(tmp_path, session_id)

    flow_7 = FlowState(issue_id="7", status=FlowStatus.dispatched)
    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = [flow_7]

    spawn_mock = _run_loop_once(session_id, config, mock_watcher=mock_watcher)

    call_args = spawn_mock.call_args
    assert call_args.args[0] == "7"


def test_watcher_loop_no_spawn_when_poll_returns_empty(tmp_path):
    config = _make_config(tmp_path)
    session_id = "perk_aa1122"
    _setup_session(tmp_path, session_id)

    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = []

    spawn_mock = _run_loop_once(session_id, config, mock_watcher=mock_watcher)

    spawn_mock.assert_not_called()


# ── Scenario: Watcher loop drains the dispatch queue after each poll ──────────

def test_watcher_loop_drains_queued_issue_when_slot_free(tmp_path):
    config = _make_config(tmp_path, max_concurrent=5)
    session_id = "perk_bb2233"
    _setup_session(tmp_path, session_id)

    # Pre-populate the queue with issue #55
    queue = DispatchQueue()
    queue.enqueue("55")

    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = []  # no fresh dispatched issues

    spawn_mock = _run_loop_once(
        session_id, config,
        mock_watcher=mock_watcher,
        queue=queue,
        initial_active_flows=0,  # slot is free
    )

    spawn_mock.assert_called_once_with("55", ANY, ANY, config)


def test_watcher_loop_drains_multiple_queued_issues_when_slots_free(tmp_path):
    config = _make_config(tmp_path, max_concurrent=5)
    session_id = "perk_bb2233"
    _setup_session(tmp_path, session_id)

    queue = DispatchQueue()
    queue.enqueue("55")
    queue.enqueue("56")

    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = []

    spawn_mock = _run_loop_once(
        session_id, config,
        mock_watcher=mock_watcher,
        queue=queue,
        initial_active_flows=0,
    )

    assert spawn_mock.call_count == 2
    called_ids = {call.args[0] for call in spawn_mock.call_args_list}
    assert called_ids == {"55", "56"}


# ── Scenario: Watcher loop does not spawn when concurrency limit reached ──────

def test_watcher_loop_does_not_spawn_when_at_concurrency_limit(tmp_path):
    config = _make_config(tmp_path, max_concurrent=2)
    session_id = "perk_cc3344"
    _setup_session(tmp_path, session_id)

    # Queue has an issue, but all slots are taken
    queue = DispatchQueue()
    queue.enqueue("56")

    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = []

    spawn_mock = _run_loop_once(
        session_id, config,
        mock_watcher=mock_watcher,
        queue=queue,
        initial_active_flows=2,  # at max_concurrent=2
    )

    spawn_mock.assert_not_called()


def test_watcher_loop_poll_once_called_with_active_flows_count(tmp_path):
    config = _make_config(tmp_path, max_concurrent=3)
    session_id = "perk_cc3344"
    _setup_session(tmp_path, session_id)

    mock_watcher = MagicMock()
    mock_watcher.poll_once.return_value = []

    _run_loop_once(
        session_id, config,
        mock_watcher=mock_watcher,
        initial_active_flows=2,
    )

    mock_watcher.poll_once.assert_called_with(2)
