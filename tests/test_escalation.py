"""
Unit tests for ask_master escalation state machine — covers:
  - Scenario: Master answers a dev sub-agent question from loaded context
  - Scenario: Master escalates an unanswerable question to the human via the issue thread
  - Scenario: Human responds on the issue thread and Master resumes the dev sub-agent
"""
from pathlib import Path

from perkins.escalation import (
    build_interrupt_payload,
    build_resume_command,
    set_flow_resumed,
    set_flow_waiting_human,
)
from perkins.models import FlowState, FlowStatus


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_flow(session_dir: Path, issue_id: str, status: FlowStatus) -> None:
    flows_dir = session_dir / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    flow = FlowState(issue_id=issue_id, status=status)
    (flows_dir / f"{issue_id}.json").write_text(flow.model_dump_json(indent=2))


# ── set_flow_waiting_human (Scenario: escalates to human) ───────────────────

def test_set_flow_waiting_human_updates_status(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.in_progress)
    set_flow_waiting_human(tmp_path, "38")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "38.json").read_text())
    assert flow.status == FlowStatus.waiting_human


def test_set_flow_waiting_human_writes_atomically(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.in_progress)
    set_flow_waiting_human(tmp_path, "38")
    assert list((tmp_path / "flows").glob("*.tmp")) == []


# ── build_interrupt_payload (Scenario: escalates — interrupt() structure) ───

def test_build_interrupt_payload_type_is_ask_master():
    payload = build_interrupt_payload("38", "What auth scheme?", "OAuth context")
    assert payload["type"] == "ask_master"


def test_build_interrupt_payload_includes_issue_id():
    payload = build_interrupt_payload("38", "What auth scheme?", "OAuth context")
    assert payload["issue_id"] == "38"


def test_build_interrupt_payload_includes_question():
    payload = build_interrupt_payload("38", "What auth scheme?", "OAuth context")
    assert payload["question"] == "What auth scheme?"


def test_build_interrupt_payload_includes_context():
    payload = build_interrupt_payload("38", "What auth scheme?", "OAuth context")
    assert payload["context"] == "OAuth context"


def test_build_interrupt_payload_has_exactly_required_keys():
    payload = build_interrupt_payload("38", "Q?", "ctx")
    assert set(payload.keys()) == {"type", "issue_id", "question", "context"}


# ── set_flow_resumed (Scenario: human responds, Master resumes) ──────────────

def test_set_flow_resumed_sets_in_progress(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.waiting_human)
    set_flow_resumed(tmp_path, "38")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "38.json").read_text())
    assert flow.status == FlowStatus.in_progress


def test_set_flow_resumed_from_waiting_human(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.waiting_human)
    set_flow_resumed(tmp_path, "38")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "38.json").read_text())
    assert flow.status != FlowStatus.waiting_human


def test_set_flow_resumed_writes_atomically(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.waiting_human)
    set_flow_resumed(tmp_path, "38")
    assert list((tmp_path / "flows").glob("*.tmp")) == []


# ── build_resume_command (Scenario: Command(resume=...) payload) ─────────────

def test_build_resume_command_has_answer_key():
    cmd = build_resume_command("Use JWT with RS256.")
    assert "answer" in cmd


def test_build_resume_command_contains_human_answer():
    answer = "Use JWT with RS256 and a 15-minute expiry."
    cmd = build_resume_command(answer)
    assert cmd["answer"] == answer


def test_build_resume_command_has_only_answer_key():
    cmd = build_resume_command("yes")
    assert set(cmd.keys()) == {"answer"}


# ── Round-trip: escalate then resume ─────────────────────────────────────────

def test_escalation_and_resume_round_trip(tmp_path):
    _write_flow(tmp_path, "38", FlowStatus.in_progress)
    set_flow_waiting_human(tmp_path, "38")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "38.json").read_text())
    assert flow.status == FlowStatus.waiting_human

    set_flow_resumed(tmp_path, "38")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "38.json").read_text())
    assert flow.status == FlowStatus.in_progress
