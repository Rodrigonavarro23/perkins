"""
Unit tests for perkins init command — covers:
  - Scenario: Init creates perkins.yaml with placeholders when no file exists
  - Scenario: Init autodetects github_repo from git remote origin
  - Scenario: Init falls back to placeholder when git remote cannot be detected
  - Scenario: Init preserves valid schema fields from an existing perkins.yaml
  - Scenario: Init strips fields not present in the PerkinsConfig schema
  - Scenario: Init aborts when gh CLI is not installed
  - Scenario: Init aborts when gh CLI is not authenticated
  - Scenario: Init aborts when cliplin.yaml is missing
  - Scenario: Init aborts when cliplin-acd knowledge package is not installed
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import yaml

from perkins.init import PLACEHOLDERS, build_config_dict, detect_github_repo


# ── Scenario: Init creates perkins.yaml with placeholders when no file exists ─

def test_build_config_dict_returns_all_required_fields_when_no_existing_config():
    """All required PerkinsConfig fields are present with placeholder values."""
    result = build_config_dict(existing={}, github_repo="owner/repo")

    assert result["repo"]["name"] == PLACEHOLDERS["repo.name"]
    assert result["repo"]["description"] == PLACEHOLDERS["repo.description"]
    assert result["repo"]["github_repo"] == "owner/repo"
    assert result["orchestrator"]["provider"] == PLACEHOLDERS["orchestrator.provider"]
    assert result["orchestrator"]["model"] == PLACEHOLDERS["orchestrator.model"]
    assert result["orchestrator"]["api_key_env"] == PLACEHOLDERS["orchestrator.api_key_env"]


def test_build_config_dict_is_valid_perkins_config():
    """The returned dict must be accepted by PerkinsConfig.model_validate."""
    from perkins.config import PerkinsConfig

    result = build_config_dict(existing={}, github_repo="owner/repo")
    # Should not raise
    config = PerkinsConfig.model_validate(result)
    assert config.repo.github_repo == "owner/repo"


def test_init_writes_perkins_yaml(tmp_path):
    """perkins init writes perkins.yaml to the current directory."""
    from perkins.init import run_init

    with patch("perkins.init.detect_github_repo", return_value="owner/repo"):
        run_init(project_dir=tmp_path)

    config_file = tmp_path / "perkins.yaml"
    assert config_file.exists()


def test_init_written_yaml_is_valid_yaml(tmp_path):
    """The written perkins.yaml must be parseable YAML."""
    from perkins.init import run_init

    with patch("perkins.init.detect_github_repo", return_value="owner/repo"):
        run_init(project_dir=tmp_path)

    content = (tmp_path / "perkins.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict)


def test_init_prints_success_message(tmp_path, capsys):
    """CLI prints a success message after creating the file."""
    from perkins.init import run_init

    with patch("perkins.init.detect_github_repo", return_value="owner/repo"):
        run_init(project_dir=tmp_path)

    captured = capsys.readouterr()
    assert "perkins.yaml" in captured.out


# ── Scenario: Init autodetects github_repo from git remote origin ─────────────

def test_detect_github_repo_parses_https_url():
    """HTTPS remote URL → 'owner/repo'."""
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://github.com/owner/myrepo.git\n"
    )
    with patch("subprocess.run", return_value=mock_result):
        result = detect_github_repo()
    assert result == "owner/myrepo"


def test_detect_github_repo_parses_ssh_url():
    """SSH remote URL → 'owner/repo'."""
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="git@github.com:owner/myrepo.git\n"
    )
    with patch("subprocess.run", return_value=mock_result):
        result = detect_github_repo()
    assert result == "owner/myrepo"


def test_detect_github_repo_strips_dot_git_suffix():
    """Trailing .git is stripped from the detected repo slug."""
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://github.com/acme/service.git\n"
    )
    with patch("subprocess.run", return_value=mock_result):
        result = detect_github_repo()
    assert result == "acme/service"


def test_init_uses_detected_github_repo_in_yaml(tmp_path):
    """github_repo in written perkins.yaml matches the autodetected value."""
    from perkins.init import run_init

    with patch("perkins.init.detect_github_repo", return_value="owner/myrepo"):
        run_init(project_dir=tmp_path)

    data = yaml.safe_load((tmp_path / "perkins.yaml").read_text(encoding="utf-8"))
    assert data["repo"]["github_repo"] == "owner/myrepo"


# ── Scenario: Init falls back to placeholder when git remote cannot be detected ─

def test_detect_github_repo_returns_placeholder_on_nonzero_exit():
    """Non-zero exit from git remote → returns placeholder 'owner/repo'."""
    with patch("subprocess.run", side_effect=subprocess.CalledProcessError(128, "git")):
        result = detect_github_repo()
    assert result == PLACEHOLDERS["repo.github_repo"]


def test_detect_github_repo_returns_placeholder_when_remote_not_configured():
    """Empty stdout from git remote → returns placeholder 'owner/repo'."""
    mock_result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="\n"
    )
    with patch("subprocess.run", return_value=mock_result):
        result = detect_github_repo()
    assert result == PLACEHOLDERS["repo.github_repo"]


def test_init_yaml_contains_placeholder_github_repo_when_no_remote(tmp_path):
    """When remote detection fails, perkins.yaml github_repo is the placeholder."""
    from perkins.init import run_init

    with patch("perkins.init.detect_github_repo", return_value=PLACEHOLDERS["repo.github_repo"]):
        run_init(project_dir=tmp_path)

    data = yaml.safe_load((tmp_path / "perkins.yaml").read_text(encoding="utf-8"))
    assert data["repo"]["github_repo"] == PLACEHOLDERS["repo.github_repo"]


# ── Scenario: Init preserves valid schema fields from an existing perkins.yaml ─

def test_build_config_dict_preserves_existing_repo_name():
    """Existing repo.name is preserved when re-running init."""
    existing = {"repo": {"name": "my-service", "github_repo": "acme/my-service"}}
    result = build_config_dict(existing=existing, github_repo="acme/my-service")
    assert result["repo"]["name"] == "my-service"


def test_build_config_dict_preserves_non_placeholder_github_repo():
    """Non-placeholder github_repo from existing config is passed through unchanged."""
    existing = {"repo": {"github_repo": "acme/my-service"}}
    result = build_config_dict(existing=existing, github_repo="acme/my-service")
    assert result["repo"]["github_repo"] == "acme/my-service"


def test_run_init_preserves_non_placeholder_github_repo(tmp_path):
    """run_init preserves existing non-placeholder github_repo — does not re-detect."""
    from perkins.init import run_init

    existing_config = {
        "repo": {"name": "my-service", "description": "desc", "github_repo": "acme/my-service"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    }
    config_path = tmp_path / "perkins.yaml"
    config_path.write_text(yaml.dump(existing_config), encoding="utf-8")

    with patch("perkins.init.detect_github_repo") as mock_detect:
        run_init(project_dir=tmp_path)
        mock_detect.assert_not_called()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["repo"]["github_repo"] == "acme/my-service"
    assert data["repo"]["name"] == "my-service"


def test_run_init_detects_github_repo_when_existing_is_placeholder(tmp_path):
    """run_init re-detects github_repo when existing value is the placeholder."""
    from perkins.init import run_init

    existing_config = {
        "repo": {"name": "my-service", "description": "desc", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    }
    config_path = tmp_path / "perkins.yaml"
    config_path.write_text(yaml.dump(existing_config), encoding="utf-8")

    with patch("perkins.init.detect_github_repo", return_value="detected/repo") as mock_detect:
        run_init(project_dir=tmp_path)
        mock_detect.assert_called_once()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["repo"]["github_repo"] == "detected/repo"


def test_build_config_dict_fills_absent_fields_with_placeholders():
    """Fields absent from existing config are filled with placeholder values."""
    existing = {"repo": {"name": "my-service"}}
    result = build_config_dict(existing=existing, github_repo=PLACEHOLDERS["repo.github_repo"])
    assert result["repo"]["description"] == PLACEHOLDERS["repo.description"]
    assert result["orchestrator"]["provider"] == PLACEHOLDERS["orchestrator.provider"]


# ── Scenario: Init strips fields not present in the PerkinsConfig schema ────────

def test_build_config_dict_strips_unrecognized_repo_fields():
    """Fields not in PerkinsConfig schema are silently dropped from output."""
    existing = {
        "repo": {"name": "my-service", "legacy_option": True},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    }
    result = build_config_dict(existing=existing, github_repo="owner/repo")
    assert "legacy_option" not in result["repo"]
    assert result["repo"]["name"] == "my-service"


def test_build_config_dict_strips_unrecognized_top_level_fields():
    """Top-level unknown keys are not propagated to the output config."""
    existing = {
        "repo": {"name": "svc", "github_repo": "owner/repo", "description": "d"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "unknown_section": {"foo": "bar"},
    }
    result = build_config_dict(existing=existing, github_repo="owner/repo")
    assert "unknown_section" not in result


def test_run_init_strips_legacy_fields_and_writes_clean_yaml(tmp_path):
    """perkins.yaml written after re-init does not contain legacy/unknown fields."""
    from perkins.init import run_init

    dirty_config = {
        "repo": {"name": "svc", "description": "d", "github_repo": "owner/repo", "legacy": True},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    }
    config_path = tmp_path / "perkins.yaml"
    config_path.write_text(yaml.dump(dirty_config), encoding="utf-8")

    with patch("perkins.init.detect_github_repo", return_value="owner/repo"):
        run_init(project_dir=tmp_path)

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "legacy" not in data.get("repo", {})
    assert data["repo"]["name"] == "svc"


# ── Dependency failure scenarios — perkins init CLI command ───────────────────

def _make_app():
    from perkins.cli import app
    return app


def test_init_aborts_when_gh_not_installed(tmp_path, monkeypatch):
    """Init CLI exits with error when gh CLI is not present in PATH."""
    from typer.testing import CliRunner
    from perkins.validation import StartupValidationError

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    with patch("perkins.cli.validate_gh_installed",
               side_effect=StartupValidationError("GitHub CLI is required. Install from: https://cli.github.com")):
        result = runner.invoke(_make_app(), ["init"])

    assert result.exit_code == 1
    assert "GitHub CLI" in result.output
    assert not (tmp_path / "perkins.yaml").exists()


def test_init_aborts_when_gh_not_authenticated(tmp_path, monkeypatch):
    """Init CLI exits with error when gh CLI is installed but not authenticated."""
    from typer.testing import CliRunner
    from perkins.validation import StartupValidationError

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated",
                side_effect=StartupValidationError("GitHub CLI not authenticated. Run: gh auth login")):
        result = runner.invoke(_make_app(), ["init"])

    assert result.exit_code == 1
    assert "gh auth login" in result.output
    assert not (tmp_path / "perkins.yaml").exists()


def test_init_aborts_when_cliplin_yaml_missing(tmp_path, monkeypatch):
    """Init CLI exits with error when cliplin.yaml is not present."""
    from typer.testing import CliRunner
    from perkins.validation import StartupValidationError

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated"), \
         patch("perkins.cli.validate_cliplin_project",
                side_effect=StartupValidationError("No cliplin.yaml found. Run: cliplin init")):
        result = runner.invoke(_make_app(), ["init"])

    assert result.exit_code == 1
    assert "cliplin" in result.output.lower()
    assert not (tmp_path / "perkins.yaml").exists()


def test_init_aborts_when_cliplin_acd_not_installed(tmp_path, monkeypatch):
    """Init CLI exits with error when cliplin-acd knowledge package is missing."""
    from typer.testing import CliRunner
    from perkins.validation import StartupValidationError

    runner = CliRunner()
    monkeypatch.chdir(tmp_path)

    with patch("perkins.cli.validate_gh_installed"), \
         patch("perkins.cli.validate_gh_authenticated"), \
         patch("perkins.cli.validate_cliplin_project"), \
         patch("perkins.cli.validate_cliplin_acd",
                side_effect=StartupValidationError("cliplin-acd package not installed")):
        result = runner.invoke(_make_app(), ["init"])

    assert result.exit_code == 1
    assert "cliplin-acd" in result.output
    assert not (tmp_path / "perkins.yaml").exists()
