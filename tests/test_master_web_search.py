"""
Unit tests for MasterOrchestrator web search resolution tier — covers:
  - Scenario: Master resolves ask_master via web search when cliplin context is insufficient
  - Scenario: Master escalates to human with search context when web search does not resolve
  - Scenario: Master falls back to direct human escalation when web search API call fails
  - Scenario: Master skips web search and escalates directly when search API key is not configured
  - Scenario: Master behavior is unchanged when search.enabled is false
Governed by: docs/tdrs/perkins-search.md, docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import asyncio
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from langgraph.types import Interrupt

from perkins.config import PerkinsConfig
from perkins.master import MasterOrchestrator


# ── fixtures ─────────────────────────────────────────────────────────────────

def _make_config(tmp_path: Path) -> PerkinsConfig:
    """Default config — search disabled."""
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


def _make_config_search_enabled(
    tmp_path: Path,
    provider: str = "brave",
    api_key_env: str = "TEST_SEARCH_KEY",
    max_results: int = 3,
) -> PerkinsConfig:
    """Config with search.enabled=true."""
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
        "search": {
            "enabled": True,
            "provider": provider,
            "api_key_env": api_key_env,
            "max_results": max_results,
        },
    })


def _mock_graph_interrupt_then_direct(interrupt_payload: dict, search_answer: str) -> MagicMock:
    """Graph that interrupts on first call, answers directly on second (search-enriched)."""
    g = MagicMock()
    g.invoke.side_effect = [
        {"__interrupt__": [Interrupt(value=interrupt_payload, id="test-id")]},
        {"answer": search_answer},
    ]
    return g


def _mock_graph_double_interrupt(payload1: dict, payload2: dict) -> MagicMock:
    """Graph interrupts on first and second (search-enriched) invocations; resumes on third."""
    g = MagicMock()
    g.invoke.side_effect = [
        {"__interrupt__": [Interrupt(value=payload1, id="test-id-1")]},
        {"__interrupt__": [Interrupt(value=payload2, id="test-id-2")]},
        {"answer": ""},  # Command(resume=...) call
    ]
    return g


def _mock_graph_always_interrupt(payload: dict) -> MagicMock:
    """Graph that always interrupts; second call resumes cleanly."""
    g = MagicMock()
    g.invoke.side_effect = [
        {"__interrupt__": [Interrupt(value=payload, id="test-id")]},
        {"answer": ""},  # resume call
    ]
    return g


def _brave_response(results: list[dict]) -> MagicMock:
    """Mock httpx response with Brave API structure."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"web": {"results": results}}
    return resp


@contextmanager
def _mock_brave_client(results: list[dict]):
    """Patch httpx.AsyncClient to return a Brave-shaped response."""
    mock_resp = _brave_response(results)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("perkins.master.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


@contextmanager
def _mock_brave_timeout():
    """Patch httpx.AsyncClient to raise TimeoutException."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with patch("perkins.master.httpx.AsyncClient", return_value=mock_client):
        yield mock_client


# ── Scenario: Master resolves ask_master via web search ──────────────────────

def test_web_search_resolves_question_returns_direct_answer(tmp_path, monkeypatch):
    """When search finds results and graph answers on second invoke, return directly."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Best practice?", "context": ""}
    mock_graph = _mock_graph_interrupt_then_direct(payload, "Use the Result pattern")
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    brave_results = [
        {"title": "Error Handling", "url": "https://example.com/err", "description": "Use Result pattern"}
    ]

    result_holder: list[str] = []

    async def _run():
        with _mock_brave_client(brave_results):
            result = await master._ask_master("42", "Best practice?", "")
            result_holder.append(result)

    asyncio.run(_run())

    assert result_holder == ["Use the Result pattern"]


def test_web_search_resolves_no_human_escalation(tmp_path, monkeypatch):
    """When search resolves, interrupt_queue is NOT populated."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_interrupt_then_direct(payload, "answer"))

    brave_results = [{"title": "T", "url": "https://u.com", "description": "s"}]

    async def _run():
        with _mock_brave_client(brave_results):
            await master._ask_master("42", "Q?", "")

    asyncio.run(_run())
    assert "42" not in master.interrupt_queues


def test_web_search_second_graph_invoke_receives_search_block(tmp_path, monkeypatch):
    """Second graph invoke must include '[WEB SEARCH RESULTS]' block in context."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": "base context"}
    mock_graph = _mock_graph_interrupt_then_direct(payload, "answer")
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    brave_results = [{"title": "T", "url": "https://u.com", "description": "snippet here"}]

    async def _run():
        with _mock_brave_client(brave_results):
            await master._ask_master("42", "Q?", "base context")

    asyncio.run(_run())

    second_call = mock_graph.invoke.call_args_list[1]
    second_context = second_call.args[0]["context"]
    assert "[WEB SEARCH RESULTS]" in second_context
    assert "T" in second_context
    assert "https://u.com" in second_context
    assert "snippet here" in second_context


def test_web_search_brave_results_normalized(tmp_path, monkeypatch):
    """Brave `description` field is mapped to `snippet` in normalized result."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)

    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_interrupt_then_direct(payload, "answer")
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    brave_results = [
        {"title": "T1", "url": "https://u1.com", "description": "desc text"},
    ]

    captured: list[list] = []

    async def _run():
        original_search = master._web_search

        async def _spy(question):
            result = await original_search(question)
            captured.append(result)
            return result

        master._web_search = _spy  # type: ignore[method-assign]
        with _mock_brave_client(brave_results):
            await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    assert len(captured) == 1
    assert captured[0] == [{"title": "T1", "url": "https://u1.com", "snippet": "desc text"}]


# ── Scenario: Master falls back when web search API call fails ────────────────

def test_web_search_timeout_falls_back_to_human_escalation(tmp_path, monkeypatch):
    """httpx.TimeoutException → graceful fallback; human is escalated normally."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("human answer")

        asyncio.create_task(_provide_answer())
        with _mock_brave_timeout():
            return await master._ask_master("42", "Q?", "")

    result = asyncio.run(_run())
    assert result == "human answer"


def test_web_search_timeout_sets_web_search_results_null_in_payload(tmp_path, monkeypatch):
    """On timeout, interrupt payload has web_search_results=null."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        with _mock_brave_timeout():
            await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    queued = master.interrupt_queues["42"].get_nowait()
    assert queued["web_search_results"] is None


def test_web_search_failure_does_not_raise(tmp_path, monkeypatch):
    """httpx errors must not propagate — MCP server must keep running."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        with _mock_brave_timeout():
            await master._ask_master("42", "Q?", "")  # must not raise

    asyncio.run(_run())  # no exception expected


def test_web_search_skip_when_api_key_unset(tmp_path):
    """When api_key_env is unset, search is skipped and escalation proceeds normally."""
    config = _make_config_search_enabled(tmp_path, api_key_env="UNSET_KEY_XYZ")
    # Do NOT set UNSET_KEY_XYZ in environment
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        return await master._ask_master("42", "Q?", "")

    result = asyncio.run(_run())
    assert result == "answer"
    queued = master.interrupt_queues["42"].get_nowait()
    assert queued["web_search_results"] is None


# ── Scenario: Master behavior unchanged when search.enabled is false ──────────

def test_search_disabled_no_web_search_performed(tmp_path):
    """With search.enabled=false (default), graph is only invoked twice (interrupt + resume)."""
    config = _make_config(tmp_path)  # search disabled by default
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_always_interrupt(payload)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        return await master._ask_master("42", "Q?", "")

    result = asyncio.run(_run())

    assert result == "answer"
    # Exactly 2 invokes: original interrupt + Command(resume) — no search invoke
    assert mock_graph.invoke.call_count == 2


def test_search_disabled_interrupt_payload_web_search_results_null(tmp_path):
    """With search disabled, web_search_results in interrupt payload is null."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    queued = master.interrupt_queues["42"].get_nowait()
    assert "web_search_results" in queued
    assert queued["web_search_results"] is None


def test_search_disabled_human_answer_still_returned(tmp_path):
    """With search disabled, ask_master still returns the human answer correctly."""
    config = _make_config(tmp_path)
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

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


# ── Scenario: Master escalates to human WITH search results when search doesn't resolve ──

def test_human_escalation_includes_web_search_results_when_second_graph_also_interrupts(
    tmp_path, monkeypatch
):
    """When search finds results but second graph invocation still interrupts,
    interrupt payload must include web_search_results with the normalized results."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload1 = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    payload2 = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    mock_graph = _mock_graph_double_interrupt(payload1, payload2)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    brave_results = [
        {"title": "Best Practice", "url": "https://example.com/bp", "description": "Use X pattern"}
    ]

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("human answer")

        asyncio.create_task(_provide_answer())
        with _mock_brave_client(brave_results):
            return await master._ask_master("42", "Q?", "")

    result = asyncio.run(_run())

    assert result == "human answer"
    queued = master.interrupt_queues["42"].get_nowait()
    assert queued["web_search_results"] == [
        {"title": "Best Practice", "url": "https://example.com/bp", "snippet": "Use X pattern"}
    ]


def test_human_escalation_with_search_results_uses_second_interrupt_payload(
    tmp_path, monkeypatch
):
    """When both invocations interrupt, the payload comes from the second (search-enriched) interrupt."""
    monkeypatch.setenv("TEST_SEARCH_KEY", "test-key")
    config = _make_config_search_enabled(tmp_path)
    payload1 = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": "first"}
    payload2 = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": "second"}
    mock_graph = _mock_graph_double_interrupt(payload1, payload2)
    master = MasterOrchestrator("perk_test", config, _graph=mock_graph)

    brave_results = [{"title": "T", "url": "https://u.com", "description": "s"}]

    async def _run():
        async def _provide_answer():
            await asyncio.sleep(0.05)
            await master.answer_queues["42"].put("answer")

        asyncio.create_task(_provide_answer())
        with _mock_brave_client(brave_results):
            await master._ask_master("42", "Q?", "")

    asyncio.run(_run())

    queued = master.interrupt_queues["42"].get_nowait()
    assert queued["context"] == "second"  # payload from second interrupt, not first


# ── Scenario: Master skips search and escalates when API key not configured ───

def test_web_search_logs_warning_when_api_key_unset(tmp_path, caplog):
    """When api_key_env is unset, a warning must be logged before skipping search."""
    import logging
    config = _make_config_search_enabled(tmp_path, api_key_env="DEFINITELY_UNSET_KEY_XYZ")
    payload = {"type": "ask_master", "issue_id": "42", "question": "Q?", "context": ""}
    master = MasterOrchestrator("perk_test", config, _graph=_mock_graph_always_interrupt(payload))

    with caplog.at_level(logging.WARNING, logger="perkins.master"):
        async def _run():
            async def _provide_answer():
                await asyncio.sleep(0.05)
                await master.answer_queues["42"].put("answer")

            asyncio.create_task(_provide_answer())
            await master._ask_master("42", "Q?", "")

        asyncio.run(_run())

    assert "search.api_key_env is unset" in caplog.text
