"""
Session crash recovery for Perkins.
Governed by: docs/tdrs/perkins-subprocess-management.md, docs/tdrs/perkins-serialization.md
"""
from __future__ import annotations

import datetime
from pathlib import Path

from perkins.models import FlowState, FlowStatus
from perkins.session import _atomic_write


def recover_session(session_dir: Path) -> list[str]:
    """
    Apply crash recovery rules to all flow files in session_dir/flows/:
      - in_progress  → failed  (subprocess was interrupted; no auto-retry)
      - waiting_human → unchanged (LangGraph checkpoint survives; re-resumes on next start)
      - completed / failed / queued / dispatched → unchanged

    Returns list of recovered issue IDs (those set to failed).
    Appends a recovery.log entry for each transitioned flow.
    """
    flows_dir = session_dir / "flows"
    recovered: list[str] = []

    for flow_file in sorted(flows_dir.glob("*.json")):
        flow = FlowState.model_validate_json(flow_file.read_text(encoding="utf-8"))
        if flow.status == FlowStatus.in_progress:
            flow.status = FlowStatus.failed
            _atomic_write(flow_file, flow.model_dump_json(indent=2))
            recovered.append(flow.issue_id)

    if recovered:
        _append_recovery_log(session_dir, recovered)

    return recovered


def _append_recovery_log(session_dir: Path, recovered_ids: list[str]) -> None:
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    recovery_log = session_dir / "recovery.log"
    lines = [
        f"{timestamp} RECOVERY: {len(recovered_ids)} flow(s) set to failed",
    ]
    for issue_id in recovered_ids:
        lines.append(f"{timestamp} RECOVERY: issue #{issue_id} in_progress → failed")
    with open(recovery_log, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
