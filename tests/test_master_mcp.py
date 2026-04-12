"""
Unit tests for MasterOrchestrator MCP server — covers:
  - Scenario: MCP server starts as asyncio task on the configured port
  - Scenario: ask_master tool triggers LangGraph interrupt when Master cannot answer
  - Scenario: ask_master tool returns answer directly when Master can answer from context
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.types import Interrupt

from perkins.config import PerkinsConfig
from perkins.master import MasterOrchestrator
from perkins.runtime import runtime_main


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


def _mock_graph_direct(answer: str = "direct answer") -> MagicMock:
    """Mock graph that returns an answer without interrupting."""
    g = MagicMock()
    g.invoke.return_value = {"answer": answer}
    return g


def _mock_graph_interrupt(payload: dict) -> MagicMock:
    """Mock graph that returns an __interrupt__ on first call, then resumes on second."""
    g = MagicMock()
    g.invoke.side_effect = [
        {"__interrupt__": [Interrupt(value=payload, id="test-id")]},
        {"answer": ""},  # resume call result
    ]
    return g


# ── Scenario: MCP server starts as asyncio task on the configured port ─────────

def test_master_start_returns_asyncio_task(tmp_path):
    """master.start() returns an asyncio.Task wrapping run_sse_async."""
    config = _make_config(tmp_path)
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_direct())

    async def _run():
        with patch("perkins.master.FastMCP.run_sse_async", new=AsyncMock()):
            task = master.start()
            assert isinstance(task, asyncio.Task)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())


def test_master_mcp_task_created_before_watcher_loop(tmp_path):
    """runtime_main must call master.start() before calling watcher_loop(...)."""
    config = _make_config(tmp_path)
    session_id = "perk_aabbcc"
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    session_dir.mkdir(parents=True)

    call_order: list[str] = []

    async def _run():
        mock_mcp_task = asyncio.ensure_future(asyncio.sleep(0))
        mock_master = MagicMock()
        mock_master.start.side_effect = lambda: (call_order.append("mcp") or mock_mcp_task)

        async def _watcher_coro(*a, **kw):
            pass

        def _watcher_loop_spy(*a, **kw):
            # Called synchronously when create_task(watcher_loop(...)) evaluates its arg
            call_order.append("watcher")
            return _watcher_coro()

        with patch("perkins.runtime.MasterOrchestrator", return_value=mock_master):
            with patch("perkins.runtime.watcher_loop", _watcher_loop_spy):
                with patch("perkins.runtime._get_shutdown_event") as mock_evt:
                    evt = asyncio.Event()
                    evt.set()
                    mock_evt.return_value = evt
                    await runtime_main(session_id, config)

    asyncio.run(_run())
    assert "mcp" in call_order
    assert "watcher" in call_order
    assert call_order.index("mcp") < call_order.index("watcher")


def test_master_start_uses_configured_port(tmp_path):
    """FastMCP is initialised with the port from config."""
    config = _make_config(tmp_path)
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_direct())

    async def _run():
        with patch("perkins.master.FastMCP.run_sse_async", new=AsyncMock()):
            task = master.start()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(_run())
    assert master._mcp is not None
    assert master._mcp.settings.port == 7331


# ── Scenario: ask_master triggers interrupt when Master cannot answer ──────────

def test_ask_master_puts_payload_on_interrupt_queue(tmp_path):
    """When graph returns __interrupt__, payload is placed on interrupt_queue[issue_id]."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Which pattern?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use Repository")

        asyncio.create_task(_provide_answer())
        await master._ask_master("42", "Which pattern?", "")

    asyncio.run(_run())

    assert "42" in master.interrupt_queues
    assert master.interrupt_queues["42"].qsize() == 1
    queued = master.interrupt_queues["42"].get_nowait()
    assert queued == payload


def test_ask_master_returns_human_answer_after_interrupt(tmp_path):
    """ask_master returns the answer from answer_queue after interrupt is resolved."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_interrupt(payload))

    result_holder: list[str] = []

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use Repository")

        asyncio.create_task(_provide_answer())
        result = await master._ask_master("42", "Q?", "")
        result_holder.append(result)

    asyncio.run(_run())
    assert result_holder == ["Use Repository"]


def test_ask_master_resumes_graph_with_command_after_interrupt(tmp_path):
    """ask_master calls graph.invoke(Command(resume=...)) after receiving the answer."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_interrupt(payload)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("Use Repository")

        asyncio.create_task(_provide_answer())
        await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    from langgraph.types import Command
    assert mock_graph.invoke.call_count == 2
    second_call_args = mock_graph.invoke.call_args_list[1]
    cmd = second_call_args.args[0]
    assert isinstance(cmd, Command)
    assert cmd.resume == {"answer": "Use Repository"}


# ── Scenario: ask_master returns answer directly when Master can answer ────────

def test_ask_master_returns_direct_answer_without_interrupt(tmp_path):
    """When graph answers directly, ask_master returns without touching interrupt_queues."""
    config = _make_config(tmp_path)
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_direct("direct answer"))

    result_holder: list[str] = []

    async def _run():
        result = await master._ask_master("42", "easy question", "")
        result_holder.append(result)

    asyncio.run(_run())
    assert result_holder == ["direct answer"]


def test_ask_master_does_not_populate_interrupt_queue_on_direct_answer(tmp_path):
    """No interrupt_queue entry is created when graph answers directly."""
    config = _make_config(tmp_path)
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_direct())

    async def _run():
        await master._ask_master("42", "easy question", "")

    asyncio.run(_run())
    assert "42" not in master.interrupt_queues
