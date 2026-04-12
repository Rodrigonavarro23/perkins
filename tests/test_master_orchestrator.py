"""
Unit tests for MasterOrchestrator initialization and perkins chat resume — covers:
  - Scenario: Master Orchestrator is created with SqliteSaver and session thread_id
  - Scenario: perkins chat resumes interrupted Master with human answer
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command, Interrupt

from perkins.config import PerkinsConfig
from perkins.master import MasterOrchestrator


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


def _mock_graph_direct(answer: str = "direct answer") -> MagicMock:
    g = MagicMock()
    g.invoke.return_value = {"answer": answer}
    return g


def _mock_graph_interrupt(payload: dict) -> MagicMock:
    g = MagicMock()
    g.invoke.side_effect = [
        {"__interrupt__": [Interrupt(value=payload, id="test-id")]},
        {"answer": ""},
    ]
    return g


# ── Scenario: Master Orchestrator created with SqliteSaver and session thread_id ─

def test_master_calls_create_deep_agent_with_sqlite_saver(tmp_path):
    """MasterOrchestrator.__init__ must call create_deep_agent() with a SqliteSaver checkpointer."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    config = _make_config(tmp_path)
    session_id = "perk_a1b2c3"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    with patch("perkins.master.create_deep_agent") as mock_create:
        mock_create.return_value = MagicMock()
        MasterOrchestrator(session_id, config)

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert "checkpointer" in call_kwargs
    assert isinstance(call_kwargs["checkpointer"], SqliteSaver)


def test_master_graph_db_created_at_session_path(tmp_path):
    """SqliteSaver checkpointer DB must be at .perkins/sessions/{session_id}/graph.db."""
    config = _make_config(tmp_path)
    session_id = "perk_a1b2c3"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)
    expected_db = session_dir / "graph.db"

    with patch("perkins.master.create_deep_agent", return_value=MagicMock()):
        MasterOrchestrator(session_id, config)

    assert expected_db.exists(), f"graph.db must exist at {expected_db}"


def test_master_uses_session_id_as_thread_id(tmp_path):
    """All graph.invoke() calls must use session_id as thread_id in the config."""
    config = _make_config(tmp_path)
    session_id = "perk_a1b2c3"
    mock_graph = _mock_graph_direct("ans")
    master = MasterOrchestrator(session_id, config, _graph=mock_graph)

    async def _run():
        return await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    cfg_arg = mock_graph.invoke.call_args.args[1]
    assert cfg_arg["configurable"]["thread_id"] == session_id


def test_master_initial_invoke_passes_version_v2(tmp_path):
    """The initial graph.invoke() call (not resume) must pass version='v2'."""
    config = _make_config(tmp_path)
    mock_graph = _mock_graph_direct("ans")
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    async def _run():
        return await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    call = mock_graph.invoke.call_args_list[0]
    assert call.kwargs.get("version") == "v2", (
        f"Expected version='v2' in initial invoke call, got: {call.kwargs}"
    )


# ── Scenario: perkins chat resumes interrupted Master with human answer ────────

def test_perkins_chat_resume_invoke_passes_command_and_version_v2(tmp_path):
    """Resume invoke must use Command(resume=...) and version='v2'."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_interrupt(payload)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    async def _run():
        async def _simulate_chat():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use the Repository pattern")

        asyncio.create_task(_simulate_chat())
        return await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    # Verify resume call
    resume_call = mock_graph.invoke.call_args_list[1]
    cmd = resume_call.args[0]
    assert isinstance(cmd, Command)
    assert cmd.resume == {"answer": "Use the Repository pattern"}
    assert resume_call.kwargs.get("version") == "v2", (
        f"Expected version='v2' in resume invoke call, got: {resume_call.kwargs}"
    )


def test_perkins_chat_resume_answer_placed_on_answer_queue(tmp_path):
    """After perkins chat provides the answer, it is placed on answer_queues[issue_id]."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_interrupt(payload)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    answer_received: list[str] = []

    async def _run():
        async def _simulate_chat():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use the Repository pattern")

        asyncio.create_task(_simulate_chat())
        result = await master._ask_master("42", "Q?", "")
        answer_received.append(result)

    asyncio.run(_run())

    assert answer_received == ["Use the Repository pattern"]


def test_perkins_chat_resume_ask_master_returns_answer(tmp_path):
    """ask_master handler must return the answer after the chat resume resolves."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_interrupt(payload)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    async def _run():
        async def _simulate_chat():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use the Repository pattern")

        asyncio.create_task(_simulate_chat())
        return await master._ask_master("42", "Q?", "")

    result = asyncio.run(_run())
    assert result == "Use the Repository pattern"
