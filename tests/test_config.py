"""
Unit tests for PerkinsConfig — covers:
  - Scenario: Starting with an invalid perkins.yaml exits with a validation error
  - Scenario: Starting with out-of-range perkins.yaml values exits with a validation error
"""
import pytest
from pydantic import ValidationError

from perkins.config import PerkinsConfig


def _valid_data(**overrides) -> dict:
    base = {
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
    base.update(overrides)
    return base


# ── Happy path ────────────────────────────────────────────────────────────────

def test_valid_config_parses_with_defaults():
    config = PerkinsConfig.model_validate(_valid_data())
    assert config.repo.github_repo == "owner/repo"
    assert config.dev_agents.max_concurrent == 5
    assert config.dev_agents.cleanup_worktree_on == "issue_closed"
    assert config.mcp_server.port == 7331


# ── Scenario: Starting with an invalid perkins.yaml exits with a validation error ──

def test_missing_github_repo_raises_validation_error():
    data = _valid_data()
    del data["repo"]["github_repo"]
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "github_repo" in str(exc_info.value)


def test_missing_repo_section_raises_validation_error():
    data = _valid_data()
    del data["repo"]
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "repo" in str(exc_info.value)


def test_missing_orchestrator_section_raises_validation_error():
    data = _valid_data()
    del data["orchestrator"]
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "orchestrator" in str(exc_info.value)


# ── Scenario: Starting with out-of-range perkins.yaml values exits with a validation error ──

def test_max_concurrent_zero_raises_validation_error():
    data = _valid_data(dev_agents={"max_concurrent": 0})
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "max_concurrent" in str(exc_info.value)


def test_max_concurrent_negative_raises_validation_error():
    data = _valid_data(dev_agents={"max_concurrent": -1})
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "max_concurrent" in str(exc_info.value)


def test_invalid_cleanup_policy_raises_validation_error():
    data = _valid_data(dev_agents={"cleanup_worktree_on": "invalid"})
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "cleanup_worktree_on" in str(exc_info.value)


def test_compaction_threshold_above_one_raises_validation_error():
    data = _valid_data(session={"compaction_threshold": 1.5})
    with pytest.raises(ValidationError) as exc_info:
        PerkinsConfig.model_validate(data)
    assert "compaction_threshold" in str(exc_info.value)
