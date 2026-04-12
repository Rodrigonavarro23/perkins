"""
Unit tests for perkins summary — covers:
  - Scenario: perkins summary produces a human-readable project context snapshot
"""
from perkins.config import PerkinsConfig
from perkins.summary import build_summary_text


def _make_config(name: str = "my-service", description: str = "A cool service") -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": name, "description": description, "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
    })


def _sample_context() -> dict:
    return {
        "stack": "Python 3.13, Typer, Pydantic v2",
        "responsibilities": [
            "Autonomous issue resolution via dev sub-agents",
            "Session state management in .perkins/",
        ],
        "key_decisions": [
            {"summary": "Use gh CLI for all GitHub operations", "source": "docs/tdrs/perkins-github-operations.md"},
            {"summary": "Pydantic v2 for all serialization", "source": "docs/tdrs/perkins-serialization.md"},
        ],
    }


# ── Repo identity ─────────────────────────────────────────────────────────────

def test_summary_includes_repo_name():
    text = build_summary_text(_make_config(name="my-service"), _sample_context())
    assert "my-service" in text


def test_summary_includes_repo_description():
    text = build_summary_text(_make_config(description="Resolves GitHub issues autonomously"), _sample_context())
    assert "Resolves GitHub issues autonomously" in text


# ── Technology stack ──────────────────────────────────────────────────────────

def test_summary_includes_stack():
    text = build_summary_text(_make_config(), _sample_context())
    assert "Python 3.13" in text


def test_summary_includes_full_stack_string():
    ctx = {"stack": "Go 1.22, Gin, GORM", "responsibilities": [], "key_decisions": []}
    text = build_summary_text(_make_config(), ctx)
    assert "Go 1.22" in text


# ── Responsibilities ──────────────────────────────────────────────────────────

def test_summary_includes_responsibilities():
    text = build_summary_text(_make_config(), _sample_context())
    assert "Autonomous issue resolution" in text


def test_summary_includes_all_responsibilities():
    text = build_summary_text(_make_config(), _sample_context())
    assert "Session state management" in text


def test_summary_handles_empty_responsibilities():
    ctx = {"stack": "Python", "responsibilities": [], "key_decisions": []}
    text = build_summary_text(_make_config(), ctx)
    assert "my-service" in text  # still renders without crashing


# ── Key decisions ─────────────────────────────────────────────────────────────

def test_summary_includes_key_decision_summary():
    text = build_summary_text(_make_config(), _sample_context())
    assert "gh CLI" in text


def test_summary_includes_key_decision_source():
    text = build_summary_text(_make_config(), _sample_context())
    assert "perkins-github-operations" in text


def test_summary_includes_all_key_decisions():
    text = build_summary_text(_make_config(), _sample_context())
    assert "Pydantic v2" in text
    assert "perkins-serialization" in text


def test_summary_handles_empty_key_decisions():
    ctx = {"stack": "Python", "responsibilities": ["does stuff"], "key_decisions": []}
    text = build_summary_text(_make_config(), ctx)
    assert "does stuff" in text


# ── build_summary_json (Scenario: perkins summary --json) ────────────────────

from perkins.summary import build_summary_json  # noqa: E402


def test_summary_json_has_required_top_level_keys():
    result = build_summary_json(_make_config(), _sample_context())
    assert set(result.keys()) == {"repo", "stack", "responsibilities", "key_decisions"}


def test_summary_json_repo_name_matches_config():
    result = build_summary_json(_make_config(name="svc-x"), _sample_context())
    assert result["repo"]["name"] == "svc-x"


def test_summary_json_repo_description_matches_config():
    result = build_summary_json(_make_config(description="Does X"), _sample_context())
    assert result["repo"]["description"] == "Does X"


def test_summary_json_repo_github_repo_present():
    result = build_summary_json(_make_config(), _sample_context())
    assert result["repo"]["github_repo"] == "owner/repo"


def test_summary_json_stack_matches_context():
    result = build_summary_json(_make_config(), _sample_context())
    assert result["stack"] == "Python 3.13, Typer, Pydantic v2"


def test_summary_json_responsibilities_is_list():
    result = build_summary_json(_make_config(), _sample_context())
    assert isinstance(result["responsibilities"], list)


def test_summary_json_key_decisions_contain_source():
    result = build_summary_json(_make_config(), _sample_context())
    sources = [kd["source"] for kd in result["key_decisions"]]
    assert any("perkins-github-operations" in s for s in sources)


def test_summary_json_is_json_serialisable():
    import json as _json
    result = build_summary_json(_make_config(), _sample_context())
    serialised = _json.dumps(result)
    roundtrip = _json.loads(serialised)
    assert roundtrip["repo"]["name"] == _make_config().repo.name
