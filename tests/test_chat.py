"""
Unit tests for perkins chat command — covers all 6 scenarios:
  - Scenario: Chat shows pending question and delivers answer to runtime
  - Scenario: Chat exits cleanly when no questions are pending
  - Scenario: Chat --watch polls until a question appears then prompts
  - Scenario: Chat prompts for each pending question when multiple are pending
  - Scenario: Chat exits with error when runtime has not started
  - Scenario: Chat exits with error when connection to runtime is refused
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_port_file(tmp_path: Path, session_id: str, port: int) -> Path:
    port_file = tmp_path / ".perkins" / "sessions" / session_id / "chat.port"
    port_file.parent.mkdir(parents=True)
    port_file.write_text(str(port), encoding="utf-8")
    return port_file


# ── Scenario: Chat exits with error when runtime has not started ───────────────

def test_chat_cli_exits_when_no_port_file(tmp_path, monkeypatch):
    """CLI exits 1 with clear message when chat.port does not exist."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["chat", "perk_abc123"])

    assert result.exit_code == 1
    assert "Runtime not running for session perk_abc123." in result.output


def test_run_chat_raises_exit_when_no_port_file(tmp_path):
    """run_chat raises typer.Exit(1) when chat.port is missing."""
    import typer
    from perkins.chat_client import run_chat

    with pytest.raises(typer.Exit) as exc_info:
        asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    assert exc_info.value.exit_code == 1


# ── Scenario: Chat exits cleanly when no questions are pending ─────────────────

def test_run_chat_prints_no_questions_and_exits_0(tmp_path, capsys):
    """run_chat prints 'No pending questions' message when interrupt list is empty."""
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=[])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    captured = capsys.readouterr()
    assert "No pending questions for session perk_abc123." in captured.out


def test_chat_cli_prints_no_questions(tmp_path, monkeypatch):
    """CLI prints 'No pending questions' when server returns empty list."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    _make_port_file(tmp_path, "perk_abc123", 9999)

    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value=[])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_response)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    runner = CliRunner()
    with patch("aiohttp.ClientSession", return_value=mock_session):
        result = runner.invoke(app, ["chat", "perk_abc123"])

    assert result.exit_code == 0
    assert "No pending questions for session perk_abc123." in result.output


# ── Scenario: Chat shows pending question and delivers answer to runtime ────────

def test_run_chat_shows_question_and_posts_answer(tmp_path, capsys):
    """run_chat shows the question, reads answer via input(), POSTs it to /answers/{issue_id}."""
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    interrupts = [{"issue_id": "42", "question": "Which pattern to use?", "context": ""}]

    # GET /interrupts response
    mock_get_resp = AsyncMock()
    mock_get_resp.json = AsyncMock(return_value=interrupts)
    mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
    mock_get_resp.__aexit__ = AsyncMock(return_value=False)

    # POST /answers/42 response
    mock_post_resp = AsyncMock()
    mock_post_resp.json = AsyncMock(return_value={"ok": True})
    mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
    mock_post_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_resp)
    mock_session.post = MagicMock(return_value=mock_post_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session), \
         patch("builtins.input", return_value="Use the Repository pattern"):
        asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    captured = capsys.readouterr()
    assert "Which pattern to use?" in captured.out
    assert "delivered" in captured.out.lower()


def test_run_chat_posts_to_correct_answer_endpoint(tmp_path):
    """run_chat POSTs the answer to /sessions/{session_id}/answers/{issue_id}."""
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    interrupts = [{"issue_id": "42", "question": "Which pattern?", "context": ""}]

    mock_get_resp = AsyncMock()
    mock_get_resp.json = AsyncMock(return_value=interrupts)
    mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
    mock_get_resp.__aexit__ = AsyncMock(return_value=False)

    mock_post_resp = AsyncMock()
    mock_post_resp.json = AsyncMock(return_value={"ok": True})
    mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
    mock_post_resp.__aexit__ = AsyncMock(return_value=False)

    posted_urls: list[str] = []
    posted_bodies: list[dict] = []

    def capture_post(url, json=None, **kwargs):
        posted_urls.append(url)
        posted_bodies.append(json or {})
        return mock_post_resp

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_resp)
    mock_session.post = MagicMock(side_effect=capture_post)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session), \
         patch("builtins.input", return_value="Use the Repository pattern"):
        asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    assert len(posted_urls) == 1
    assert "/sessions/perk_abc123/answers/42" in posted_urls[0]
    assert posted_bodies[0]["answer"] == "Use the Repository pattern"


# ── ChatServer unit tests ──────────────────────────────────────────────────────

def test_chat_server_start_writes_port_file(tmp_path):
    """ChatServer.start() writes chat.port to the session directory."""
    from perkins.chat_server import ChatServer

    session_dir = tmp_path / ".perkins" / "sessions" / "perk_abc123"
    session_dir.mkdir(parents=True)
    master = MagicMock()
    master.answer_queues = {}

    server = ChatServer("perk_abc123", session_dir, master)

    async def _run():
        await server.start()
        port_file = session_dir / "chat.port"
        assert port_file.exists()
        port = int(port_file.read_text(encoding="utf-8").strip())
        assert port > 0
        await server.stop()

    asyncio.run(_run())


def test_chat_server_stop_deletes_port_file(tmp_path):
    """ChatServer.stop() deletes the chat.port file."""
    from perkins.chat_server import ChatServer

    session_dir = tmp_path / ".perkins" / "sessions" / "perk_abc123"
    session_dir.mkdir(parents=True)
    master = MagicMock()
    master.answer_queues = {}

    server = ChatServer("perk_abc123", session_dir, master)

    async def _run():
        await server.start()
        await server.stop()
        assert not (session_dir / "chat.port").exists()

    asyncio.run(_run())


def test_chat_server_get_interrupts_returns_pending(tmp_path):
    """GET /interrupts returns registered interrupt payloads."""
    from aiohttp.test_utils import TestClient, TestServer
    from perkins.chat_server import ChatServer

    session_dir = tmp_path / ".perkins" / "sessions" / "perk_abc123"
    session_dir.mkdir(parents=True)
    master = MagicMock()
    master.answer_queues = {}

    server = ChatServer("perk_abc123", session_dir, master)
    server.register_interrupt("42", "Which pattern?", "some context")

    async def _run():
        await server.start()
        port = int((session_dir / "chat.port").read_text(encoding="utf-8").strip())
        import aiohttp
        async with aiohttp.ClientSession() as http:
            async with http.get(f"http://127.0.0.1:{port}/sessions/perk_abc123/interrupts") as resp:
                data = await resp.json()
        await server.stop()
        return data

    result = asyncio.run(_run())
    assert len(result) == 1
    assert result[0]["issue_id"] == "42"
    assert result[0]["question"] == "Which pattern?"


def test_chat_server_post_answer_puts_on_queue(tmp_path):
    """POST /answers/{issue_id} places the answer on master.answer_queues[issue_id]."""
    from perkins.chat_server import ChatServer

    session_dir = tmp_path / ".perkins" / "sessions" / "perk_abc123"
    session_dir.mkdir(parents=True)

    answer_queue: asyncio.Queue = asyncio.Queue()
    master = MagicMock()
    master.answer_queues = {"42": answer_queue}

    server = ChatServer("perk_abc123", session_dir, master)
    server.register_interrupt("42", "Which pattern?", "")

    async def _run():
        await server.start()
        port = int((session_dir / "chat.port").read_text(encoding="utf-8").strip())
        import aiohttp
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"http://127.0.0.1:{port}/sessions/perk_abc123/answers/42",
                json={"answer": "Use the Repository pattern"},
            ) as resp:
                data = await resp.json()
        await server.stop()
        return data, answer_queue

    result_data, q = asyncio.run(_run())
    assert result_data["ok"] is True
    assert not q.empty()
    answer = asyncio.run(q.get())
    assert answer == "Use the Repository pattern"


# ── Scenario: Chat prompts for each pending question when multiple are pending ─

def test_run_chat_handles_multiple_pending_interrupts(tmp_path, capsys):
    """run_chat delivers answers for all pending interrupts in FIFO order."""
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    interrupts = [
        {"issue_id": "42", "question": "Which pattern?", "context": ""},
        {"issue_id": "99", "question": "Which library?", "context": ""},
    ]

    mock_get_resp = AsyncMock()
    mock_get_resp.json = AsyncMock(return_value=interrupts)
    mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
    mock_get_resp.__aexit__ = AsyncMock(return_value=False)

    mock_post_resp = AsyncMock()
    mock_post_resp.json = AsyncMock(return_value={"ok": True})
    mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
    mock_post_resp.__aexit__ = AsyncMock(return_value=False)

    posted_urls: list[str] = []

    def capture_post(url, json=None, **kwargs):
        posted_urls.append(url)
        return mock_post_resp

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_resp)
    mock_session.post = MagicMock(side_effect=capture_post)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    answers = iter(["Answer A", "Answer B"])
    with patch("aiohttp.ClientSession", return_value=mock_session), \
         patch("builtins.input", side_effect=answers):
        asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    captured = capsys.readouterr()
    assert "Which pattern?" in captured.out
    assert "Which library?" in captured.out
    assert len(posted_urls) == 2
    assert "/answers/42" in posted_urls[0]
    assert "/answers/99" in posted_urls[1]


# ── Scenario: Chat exits with error when connection to runtime is refused ──────

def test_run_chat_exits_on_connection_refused(tmp_path):
    """run_chat raises typer.Exit(1) when aiohttp cannot connect to the runtime."""
    import typer
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        import aiohttp
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("Connection refused")
            )
        )
        mock_cls.return_value = mock_session

        with pytest.raises(typer.Exit) as exc_info:
            asyncio.run(run_chat("perk_abc123", state_dir=tmp_path / ".perkins"))

    assert exc_info.value.exit_code == 1


def test_chat_cli_prints_error_on_connection_refused(tmp_path, monkeypatch):
    """CLI prints connection error message when runtime is down."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    _make_port_file(tmp_path, "perk_abc123", 9999)

    with patch("aiohttp.ClientSession") as mock_cls:
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        import aiohttp
        mock_session.get = MagicMock(
            side_effect=aiohttp.ClientConnectorError(
                connection_key=MagicMock(), os_error=OSError("Connection refused")
            )
        )
        mock_cls.return_value = mock_session

        runner = CliRunner()
        result = runner.invoke(app, ["chat", "perk_abc123"])

    assert result.exit_code == 1
    assert "Could not connect to runtime for session perk_abc123." in result.output


# ── Scenario: Chat --watch polls until a question appears then prompts ─────────

def test_run_chat_watch_polls_until_question_arrives(tmp_path, capsys):
    """run_chat --watch polls GET /interrupts until a question is available."""
    from perkins.chat_client import run_chat

    _make_port_file(tmp_path, "perk_abc123", 9999)

    # First two calls return [], third returns a question
    call_count = 0

    async def get_json_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            return []
        return [{"issue_id": "42", "question": "Which pattern?", "context": ""}]

    mock_get_resp = AsyncMock()
    mock_get_resp.json = get_json_side_effect
    mock_get_resp.__aenter__ = AsyncMock(return_value=mock_get_resp)
    mock_get_resp.__aexit__ = AsyncMock(return_value=False)

    mock_post_resp = AsyncMock()
    mock_post_resp.json = AsyncMock(return_value={"ok": True})
    mock_post_resp.__aenter__ = AsyncMock(return_value=mock_post_resp)
    mock_post_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=mock_get_resp)
    mock_session.post = MagicMock(return_value=mock_post_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session), \
         patch("asyncio.sleep", new_callable=AsyncMock), \
         patch("builtins.input", return_value="Use the Repository pattern"):
        asyncio.run(run_chat("perk_abc123", watch=True, state_dir=tmp_path / ".perkins"))

    captured = capsys.readouterr()
    assert "Which pattern?" in captured.out
    assert call_count == 3  # polled twice before question arrived
