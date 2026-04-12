"""
Unit tests for crash recovery — covers:
  - Scenario: Perkins recovers after a crash and restores session state
"""
from pathlib import Path

from perkins.models import FlowState, FlowStatus, SessionState, SessionStatus
from perkins.recovery import recover_session


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_session(session_dir: Path, status: SessionStatus = SessionStatus.running) -> None:
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "flows").mkdir(exist_ok=True)
    state = SessionState(
        session_id=session_dir.name,
        status=status,
    )
    (session_dir / "session.json").write_text(state.model_dump_json(indent=2))


def _write_flow(session_dir: Path, issue_id: str, status: FlowStatus) -> None:
    flow = FlowState(issue_id=issue_id, status=status)
    (session_dir / "flows" / f"{issue_id}.json").write_text(flow.model_dump_json(indent=2))


def _read_flow(session_dir: Path, issue_id: str) -> FlowState:
    return FlowState.model_validate_json(
        (session_dir / "flows" / f"{issue_id}.json").read_text()
    )


# ── in_progress → failed ─────────────────────────────────────────────────────

def test_recover_sets_in_progress_flow_to_failed(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    recover_session(tmp_path)
    assert _read_flow(tmp_path, "42").status == FlowStatus.failed


def test_recover_sets_all_in_progress_flows_to_failed(tmp_path):
    _write_session(tmp_path)
    for issue_id in ("42", "43", "44"):
        _write_flow(tmp_path, issue_id, FlowStatus.in_progress)
    recover_session(tmp_path)
    for issue_id in ("42", "43", "44"):
        assert _read_flow(tmp_path, issue_id).status == FlowStatus.failed


# ── completed → untouched ────────────────────────────────────────────────────

def test_recover_does_not_touch_completed_flow(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "35", FlowStatus.completed)
    recover_session(tmp_path)
    assert _read_flow(tmp_path, "35").status == FlowStatus.completed


# ── waiting_human → stays waiting_human ─────────────────────────────────────

def test_recover_leaves_waiting_human_flow_unchanged(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "38", FlowStatus.waiting_human)
    recover_session(tmp_path)
    assert _read_flow(tmp_path, "38").status == FlowStatus.waiting_human


# ── failed → untouched ───────────────────────────────────────────────────────

def test_recover_does_not_double_fail_already_failed_flow(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "10", FlowStatus.failed)
    recover_session(tmp_path)
    assert _read_flow(tmp_path, "10").status == FlowStatus.failed


# ── mixed flows (from feature scenario) ─────────────────────────────────────

def test_recover_handles_mixed_flow_statuses(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "42", FlowStatus.in_progress)   # → failed
    _write_flow(tmp_path, "38", FlowStatus.waiting_human)  # → unchanged
    _write_flow(tmp_path, "35", FlowStatus.completed)       # → unchanged
    recover_session(tmp_path)
    assert _read_flow(tmp_path, "42").status == FlowStatus.failed
    assert _read_flow(tmp_path, "38").status == FlowStatus.waiting_human
    assert _read_flow(tmp_path, "35").status == FlowStatus.completed


# ── recovery log ─────────────────────────────────────────────────────────────

def test_recover_creates_recovery_log(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    recover_session(tmp_path)
    assert (tmp_path / "recovery.log").exists()


def test_recover_logs_failed_flows(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    recover_session(tmp_path)
    log = (tmp_path / "recovery.log").read_text()
    assert "42" in log
    assert "failed" in log.lower()


def test_recover_logs_each_recovered_flow(tmp_path):
    _write_session(tmp_path)
    for issue_id in ("42", "43"):
        _write_flow(tmp_path, issue_id, FlowStatus.in_progress)
    recover_session(tmp_path)
    log = (tmp_path / "recovery.log").read_text()
    assert "42" in log
    assert "43" in log


def test_recover_no_recovery_log_when_no_flows_to_recover(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "35", FlowStatus.completed)
    recover_session(tmp_path)
    # No in_progress flows to recover — log may or may not exist, but must not contain failure entries
    log_path = tmp_path / "recovery.log"
    if log_path.exists():
        assert "failed" not in log_path.read_text().lower()


# ── atomic writes ─────────────────────────────────────────────────────────────

def test_recover_leaves_no_tmp_files(tmp_path):
    _write_session(tmp_path)
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    recover_session(tmp_path)
    assert list((tmp_path / "flows").glob("*.tmp")) == []
