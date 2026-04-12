"""
CLI integration tests for session start/stop — covers:
  - Scenario: Starting a Perkins session returns a session ID immediately
  - Scenario: Stopping a running session gracefully persists all flow states
"""
import re
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml
from typer.testing import CliRunner

from perkins.cli import app

runner = CliRunner()


def _write_valid_perkins_yaml(path: Path) -> None:
    config = {
        "repo": {
            "name": "test-service",
            "description": "A test service",
            "github_repo": "owner/repo",
        },
        "orchestrator": {
            "provider": "anthropic",
            "model": "claude-opus-4-6",
            "api_key_env": "ANTHROPIC_API_KEY",
        },
    }
    (path / "perkins.yaml").write_text(yaml.dump(config))


def _prereqs_and_config_stack(stack: ExitStack) -> None:
    """Patch all pre-start checks so the test reaches _start_background_session."""
    for target in [
        "perkins.cli.validate_gh_installed",
        "perkins.cli.validate_gh_authenticated",
        "perkins.cli.validate_cliplin_project",
        "perkins.cli.validate_cliplin_acd",
        "perkins.cli.validate_perkins_yaml",
        "perkins.cli.validate_api_key",
        "perkins.cli._load_config",
    ]:
        stack.enter_context(patch(target))


# ── Scenario: Starting a Perkins session returns a session ID immediately ───

def test_start_prints_session_id_to_stdout():
    with ExitStack() as stack:
        _prereqs_and_config_stack(stack)
        stack.enter_context(
            patch("perkins.cli._start_background_session", return_value="perk_a3f9c2")
        )
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    assert "SESSION_ID: perk_a3f9c2" in result.output


def test_start_session_id_format_in_output():
    with ExitStack() as stack:
        _prereqs_and_config_stack(stack)
        stack.enter_context(
            patch("perkins.cli._start_background_session", return_value="perk_f00ba4")
        )
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    # Verify a session ID pattern appears in output
    assert re.search(r"perk_[a-f0-9]{6}", result.output)


def test_start_prints_attach_hint():
    with ExitStack() as stack:
        _prereqs_and_config_stack(stack)
        stack.enter_context(
            patch("perkins.cli._start_background_session", return_value="perk_a3f9c2")
        )
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    assert "perkins chat perk_a3f9c2" in result.output


def test_start_calls_background_session_exactly_once():
    with ExitStack() as stack:
        _prereqs_and_config_stack(stack)
        mock_bg = stack.enter_context(
            patch("perkins.cli._start_background_session", return_value="perk_a3f9c2")
        )
        runner.invoke(app, ["start"])
    mock_bg.assert_called_once()


# ── Scenario: Stopping a running session gracefully persists all flow states ─

def test_stop_calls_stop_session_with_provided_id():
    with patch("perkins.cli.stop_session") as mock_stop, \
         patch("perkins.cli._load_config"):
        result = runner.invoke(app, ["stop", "perk_a3f9c2"])
    assert result.exit_code == 0
    mock_stop.assert_called_once()
    call_args = mock_stop.call_args[0]
    assert call_args[0] == "perk_a3f9c2"


def test_stop_exits_zero_on_success():
    with patch("perkins.cli.stop_session"), \
         patch("perkins.cli._load_config"):
        result = runner.invoke(app, ["stop", "perk_a3f9c2"])
    assert result.exit_code == 0


def test_stop_requires_session_id():
    result = runner.invoke(app, ["stop"])
    # Without a session ID, should exit non-zero (missing argument)
    assert result.exit_code != 0
