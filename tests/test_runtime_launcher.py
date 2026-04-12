"""
Unit tests for perkins runtime launcher — covers:
  - Scenario: _start_background_session launches a detached runtime process
  - Scenario: _start_background_session raises RuntimeError if Popen fails
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perkins.config import PerkinsConfig
from perkins.runtime_launcher import start_background_session


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "my-service", "description": "desc", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
    })


# ── Scenario: detached runtime process ───────────────────────────────────────

def test_start_background_session_calls_popen_with_start_new_session(tmp_path):
    config = _make_config(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    with patch("perkins.runtime_launcher.subprocess.Popen", return_value=fake_proc) as mock_popen:
        session_id = start_background_session(config, config_path=Path("perkins.yaml"))

    mock_popen.assert_called_once()
    call_kwargs = mock_popen.call_args
    assert call_kwargs.kwargs.get("start_new_session") is True
    assert call_kwargs.kwargs.get("close_fds") is True


def test_start_background_session_invokes_perkins_runtime_module(tmp_path):
    config = _make_config(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    with patch("perkins.runtime_launcher.subprocess.Popen", return_value=fake_proc) as mock_popen:
        start_background_session(config, config_path=Path("perkins.yaml"))

    cmd = mock_popen.call_args.args[0]
    assert sys.executable in cmd
    assert "-m" in cmd
    assert "perkins.runtime" in cmd


def test_start_background_session_returns_session_id_immediately(tmp_path):
    config = _make_config(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 99999

    with patch("perkins.runtime_launcher.subprocess.Popen", return_value=fake_proc):
        session_id = start_background_session(config, config_path=Path("perkins.yaml"))

    assert session_id.startswith("perk_")
    assert len(session_id) == 11


def test_start_background_session_writes_pid_file(tmp_path):
    config = _make_config(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 42

    with patch("perkins.runtime_launcher.subprocess.Popen", return_value=fake_proc):
        session_id = start_background_session(config, config_path=Path("perkins.yaml"))

    pid_file = tmp_path / ".perkins" / "sessions" / session_id / "runtime.pid"
    assert pid_file.exists()
    assert pid_file.read_text().strip() == "42"


# ── Scenario: Popen fails with OSError ───────────────────────────────────────

def test_start_background_session_raises_runtime_error_on_oserror(tmp_path):
    config = _make_config(tmp_path)

    with patch("perkins.runtime_launcher.subprocess.Popen", side_effect=OSError("interpreter not found")):
        with pytest.raises(RuntimeError) as exc_info:
            start_background_session(config, config_path=Path("perkins.yaml"))

    assert isinstance(exc_info.value.__cause__, OSError)
