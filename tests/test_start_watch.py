"""
Unit tests for perkins start --watch flag — covers:
  - Scenario: perkins start --watch starts the session and enters interactive chat
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml


def _write_perkins_yaml(tmp_path: Path) -> None:
    config = {
        "repo": {"name": "svc", "description": "d", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    }
    (tmp_path / "perkins.yaml").write_text(yaml.dump(config), encoding="utf-8")


# ── Scenario: perkins start --watch starts the session and enters chat ─────────

def test_start_watch_calls_run_chat_with_watch_true(tmp_path, monkeypatch):
    """start --watch invokes run_chat(session_id, watch=True) after launching session."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    _write_perkins_yaml(tmp_path)

    run_chat_calls: list[dict] = []

    async def mock_run_chat(session_id, watch=False, **kwargs):
        run_chat_calls.append({"session_id": session_id, "watch": watch})

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated"), \
         patch("perkins.cli.validate_cliplin_project"), \
         patch("perkins.cli.validate_cliplin_acd"), \
         patch("perkins.cli.validate_perkins_yaml"), \
         patch("perkins.cli.validate_api_key"), \
         patch("perkins.cli._start_background_session", return_value="perk_abc123"), \
         patch("perkins.chat_client.run_chat", side_effect=mock_run_chat):
        runner = CliRunner()
        result = runner.invoke(app, ["start", "--watch"])

    assert result.exit_code == 0
    assert len(run_chat_calls) == 1
    assert run_chat_calls[0]["session_id"] == "perk_abc123"
    assert run_chat_calls[0]["watch"] is True


def test_start_watch_prints_session_id_before_entering_chat(tmp_path, monkeypatch):
    """start --watch prints the session ID before blocking in chat."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    _write_perkins_yaml(tmp_path)

    async def mock_run_chat(session_id, watch=False, **kwargs):
        pass

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated"), \
         patch("perkins.cli.validate_cliplin_project"), \
         patch("perkins.cli.validate_cliplin_acd"), \
         patch("perkins.cli.validate_perkins_yaml"), \
         patch("perkins.cli.validate_api_key"), \
         patch("perkins.cli._start_background_session", return_value="perk_abc123"), \
         patch("perkins.chat_client.run_chat", side_effect=mock_run_chat):
        runner = CliRunner()
        result = runner.invoke(app, ["start", "--watch"])

    assert "perk_abc123" in result.output
    assert "SESSION_ID" in result.output


def test_start_without_watch_does_not_call_run_chat(tmp_path, monkeypatch):
    """start without --watch does NOT enter chat mode."""
    from typer.testing import CliRunner
    from perkins.cli import app

    monkeypatch.chdir(tmp_path)
    _write_perkins_yaml(tmp_path)

    run_chat_calls: list = []

    async def mock_run_chat(session_id, watch=False, **kwargs):
        run_chat_calls.append(session_id)

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated"), \
         patch("perkins.cli.validate_cliplin_project"), \
         patch("perkins.cli.validate_cliplin_acd"), \
         patch("perkins.cli.validate_perkins_yaml"), \
         patch("perkins.cli.validate_api_key"), \
         patch("perkins.cli._start_background_session", return_value="perk_abc123"), \
         patch("perkins.chat_client.run_chat", side_effect=mock_run_chat):
        runner = CliRunner()
        result = runner.invoke(app, ["start"])

    assert result.exit_code == 0
    assert run_chat_calls == []
