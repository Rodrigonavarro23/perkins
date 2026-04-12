"""
ask_master escalation state machine for Perkins.
Governed by: docs/tdrs/perkins-agent-orchestration.md, docs/tdrs/perkins-serialization.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from perkins.models import FlowState, FlowStatus
from perkins.session import _atomic_write


def _flow_file(session_dir: Path, issue_id: str) -> Path:
    return session_dir / "flows" / f"{issue_id}.json"


# ── Flow state transitions ───────────────────────────────────────────────────

def set_flow_waiting_human(session_dir: Path, issue_id: str) -> None:
    """
    Transition a flow to waiting_human when the Master cannot answer
    from context and must escalate to the human via the issue thread.
    """
    path = _flow_file(session_dir, issue_id)
    flow = FlowState.model_validate_json(path.read_text(encoding="utf-8"))
    flow.status = FlowStatus.waiting_human
    _atomic_write(path, flow.model_dump_json(indent=2))


def set_flow_resumed(session_dir: Path, issue_id: str) -> None:
    """
    Transition a flow from waiting_human back to in_progress after
    the human has responded on the issue thread.
    """
    path = _flow_file(session_dir, issue_id)
    flow = FlowState.model_validate_json(path.read_text(encoding="utf-8"))
    flow.status = FlowStatus.in_progress
    _atomic_write(path, flow.model_dump_json(indent=2))


# ── LangGraph interrupt / resume payloads ───────────────────────────────────

def build_interrupt_payload(issue_id: str, question: str, context: str) -> dict[str, Any]:
    """
    Build the interrupt() payload for ask_master escalation.
    Structure required by perkins-agent-orchestration TDR:
      {"type": "ask_master", "issue_id": str, "question": str, "context": str}
    """
    return {
        "type": "ask_master",
        "issue_id": issue_id,
        "question": question,
        "context": context,
    }


def build_resume_command(answer: str) -> dict[str, str]:
    """
    Build the Command(resume=...) payload to resume the Master graph
    after a human response has been received.
    """
    return {"answer": answer}
