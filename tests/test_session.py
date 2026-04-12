"""
Unit tests for session lifecycle — covers:
  - Scenario: Starting a Perkins session returns a session ID immediately
  - Scenario: Stopping a running session gracefully persists all flow states
"""
import re
from pathlib import Path

import pytest

from perkins.config import PerkinsConfig
from perkins.models import FlowState, FlowStatus, SessionState, SessionStatus
from perkins.session import generate_session_id, start_session, stop_session


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "test", "description": "d", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
    })


# ── generate_session_id ─────────────────────────────────────────────────────

def test_generate_session_id_matches_format():
    sid = generate_session_id()
    assert re.fullmatch(r"perk_[a-f0-9]{6}", sid), f"Unexpected format: {sid}"


def test_generate_session_ids_are_unique():
    ids = {generate_session_id() for _ in range(50)}
    assert len(ids) == 50


# ── start_session ───────────────────────────────────────────────────────────

def test_start_session_returns_valid_session_id(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    assert re.fullmatch(r"perk_[a-f0-9]{6}", session_id)


def test_start_session_creates_session_directory(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    assert session_dir.is_dir()


def test_start_session_creates_flows_subdirectory(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    flows_dir = tmp_path / ".perkins" / "sessions" / session_id / "flows"
    assert flows_dir.is_dir()


def test_start_session_writes_session_json(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    session_file = tmp_path / ".perkins" / "sessions" / session_id / "session.json"
    assert session_file.exists()


def test_start_session_json_is_valid_state(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    session_file = tmp_path / ".perkins" / "sessions" / session_id / "session.json"
    state = SessionState.model_validate_json(session_file.read_text())
    assert state.session_id == session_id
    assert state.status == SessionStatus.running


def test_start_session_leaves_no_tmp_files(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    assert list(session_dir.glob("*.tmp")) == []


# ── stop_session ────────────────────────────────────────────────────────────

def test_stop_session_sets_status_to_completed(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    stop_session(session_id, config)
    session_file = tmp_path / ".perkins" / "sessions" / session_id / "session.json"
    state = SessionState.model_validate_json(session_file.read_text())
    assert state.status == SessionStatus.completed


def test_stop_session_persists_active_flow_files(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    flows_dir = tmp_path / ".perkins" / "sessions" / session_id / "flows"

    # Write two active flow files (simulating in-progress flows)
    for issue_id in ("42", "55"):
        flow = FlowState(issue_id=issue_id, status=FlowStatus.in_progress)
        (flows_dir / f"{issue_id}.json").write_text(flow.model_dump_json(indent=2))

    stop_session(session_id, config)

    for issue_id in ("42", "55"):
        flow_file = flows_dir / f"{issue_id}.json"
        assert flow_file.exists(), f"Flow file for issue {issue_id} missing after stop"
        persisted = FlowState.model_validate_json(flow_file.read_text())
        assert persisted.issue_id == issue_id


def test_stop_session_leaves_no_tmp_files(tmp_path):
    config = _make_config(tmp_path)
    session_id = start_session(config)
    stop_session(session_id, config)
    session_dir = tmp_path / ".perkins" / "sessions" / session_id
    assert list(session_dir.glob("*.tmp")) == []
