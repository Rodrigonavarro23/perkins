"""
Domain state models for Perkins sessions and flows.
Governed by: docs/tdrs/perkins-serialization.md, docs/tdrs/perkins-flow-lifecycle.md
"""
from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class FlowStatus(str, Enum):
    dispatched = "dispatched"
    queued = "queued"
    in_progress = "in_progress"
    waiting_human = "waiting_human"
    completed = "completed"
    failed = "failed"


class SessionStatus(str, Enum):
    running = "running"
    completed = "completed"
    interrupted = "interrupted"


class ProgressEntry(BaseModel):
    timestamp: str
    message: str


class FlowState(BaseModel):
    issue_id: str
    status: FlowStatus = FlowStatus.dispatched
    pr_url: Optional[str] = None
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)
    progress_entries: list[ProgressEntry] = Field(default_factory=list)
    issue_body: Optional[str] = None


class SessionState(BaseModel):
    session_id: str
    status: SessionStatus = SessionStatus.running
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)
