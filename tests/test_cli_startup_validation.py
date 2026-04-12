"""
CLI integration tests for startup validation — covers:
  - Scenario: Starting without gh CLI installed exits with an actionable error
  - Scenario: Starting with an invalid perkins.yaml exits with a validation error
  - Scenario: Starting with out-of-range perkins.yaml values exits with a validation error
"""
import yaml
from contextlib import ExitStack
from typer.testing import CliRunner
from unittest.mock import patch

from perkins.cli import app

runner = CliRunner()


def _write_valid_perkins_yaml(path, **overrides) -> None:
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
    config.update(overrides)
    (path / "perkins.yaml").write_text(yaml.dump(config))


def _prereqs_stack(stack: ExitStack) -> None:
    """Enter patches for all checks that precede config loading.
    Targets perkins.cli.* because CLI uses 'from perkins.validation import ...'."""
    for target in [
        "perkins.cli.validate_gh_installed",
        "perkins.cli.validate_gh_authenticated",
        "perkins.cli.validate_cliplin_project",
        "perkins.cli.validate_cliplin_acd",
        "perkins.cli.validate_perkins_yaml",
    ]:
        stack.enter_context(patch(target))


# ── Scenario: Starting without gh CLI installed exits with an actionable error ──

def test_start_without_gh_cli_exits_with_code_1(tmp_path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        with patch("perkins.cli.validate_gh_installed",
                   side_effect=__import__("perkins.validation", fromlist=["StartupValidationError"])
                   .StartupValidationError("GitHub CLI is required. Install from: https://cli.github.com")):
            result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "GitHub CLI is required" in result.output
    assert "https://cli.github.com" in result.output


def test_start_without_gh_cli_starts_no_background_processes(tmp_path):
    from perkins.validation import StartupValidationError
    with runner.isolated_filesystem(temp_dir=tmp_path):
        with patch("perkins.cli.validate_gh_installed",
                   side_effect=StartupValidationError(
                       "GitHub CLI is required. Install from: https://cli.github.com")):
            with patch("perkins.cli._start_background_session") as mock_bg:
                result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    mock_bg.assert_not_called()


# ── Scenario: Starting with an invalid perkins.yaml exits with a validation error ──

def _make_validation_error(invalid_data: dict):
    """Produce a real Pydantic ValidationError from invalid config data."""
    from pydantic import ValidationError
    from perkins.config import PerkinsConfig
    try:
        PerkinsConfig.model_validate(invalid_data)
    except ValidationError as e:
        return e
    raise AssertionError("Expected ValidationError was not raised")


def test_start_with_missing_github_repo_exits_with_code_1():
    exc = _make_validation_error({
        "repo": {"name": "test", "description": "d"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    })
    with ExitStack() as stack:
        _prereqs_stack(stack)
        stack.enter_context(patch("perkins.cli._load_config", side_effect=exc))
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "github_repo" in result.output


def test_start_with_missing_github_repo_starts_no_background_processes():
    exc = _make_validation_error({
        "repo": {"name": "test", "description": "d"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    })
    with ExitStack() as stack:
        _prereqs_stack(stack)
        stack.enter_context(patch("perkins.cli._load_config", side_effect=exc))
        mock_bg = stack.enter_context(patch("perkins.cli._start_background_session"))
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    mock_bg.assert_not_called()


# ── Scenario: Starting with out-of-range perkins.yaml values exits with a validation error ──

def test_start_with_negative_max_concurrent_exits_with_code_1():
    exc = _make_validation_error({
        "repo": {"name": "test", "description": "d", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "dev_agents": {"max_concurrent": -1},
    })
    with ExitStack() as stack:
        _prereqs_stack(stack)
        stack.enter_context(patch("perkins.cli._load_config", side_effect=exc))
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "max_concurrent" in result.output


def test_start_with_invalid_cleanup_policy_exits_with_code_1():
    exc = _make_validation_error({
        "repo": {"name": "test", "description": "d", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "dev_agents": {"cleanup_worktree_on": "never"},
    })
    with ExitStack() as stack:
        _prereqs_stack(stack)
        stack.enter_context(patch("perkins.cli._load_config", side_effect=exc))
        result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "cleanup_worktree_on" in result.output
