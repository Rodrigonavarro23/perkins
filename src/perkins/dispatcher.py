"""
FlowDispatcher and DispatchQueue — issue dispatch logic for Perkins.
Governed by: docs/tdrs/perkins-flow-lifecycle.md, docs/tdrs/perkins-serialization.md
"""
from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from perkins.models import FlowState, FlowStatus
from perkins.session import _atomic_write
from perkins.watcher import IssueRegistry


class DispatchQueue:
    """
    In-memory FIFO queue for issues that could not be immediately dispatched
    due to the max_concurrent limit. Not persisted; re-dispatched by the
    Watcher's next poll after a crash (per perkins-flow-lifecycle TDR).
    """

    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def enqueue(self, issue_id: str) -> None:
        """Add issue to the back of the queue."""
        self._queue.append(issue_id)

    def dequeue(self) -> Optional[str]:
        """Remove and return the next issue, or None if empty."""
        return self._queue.popleft() if self._queue else None

    def is_queued(self, issue_id: str) -> bool:
        return issue_id in self._queue

    def size(self) -> int:
        return len(self._queue)


class FlowDispatcher:
    """
    Decides whether to dispatch an issue immediately (status: dispatched)
    or queue it (status: queued) based on the current active flow count vs
    max_concurrent. In both cases: writes the flow JSON and tracks the issue
    in the IssueRegistry.
    """

    def __init__(
        self,
        registry: IssueRegistry,
        queue: DispatchQueue,
        max_concurrent: int,
    ) -> None:
        self._registry = registry
        self._queue = queue
        self._max_concurrent = max_concurrent

    def dispatch(
        self, issue_id: str, session_dir: Path, active_flows_count: int
    ) -> FlowState:
        """
        Create a flow entry for issue_id. If active_flows_count < max_concurrent,
        status is 'dispatched'; otherwise 'queued' and the issue is enqueued.
        Always tracks the issue in the IssueRegistry.
        """
        if active_flows_count < self._max_concurrent:
            status = FlowStatus.dispatched
        else:
            status = FlowStatus.queued
            self._queue.enqueue(issue_id)

        self._registry.track(issue_id)

        flow = FlowState(issue_id=issue_id, status=status)
        flows_dir = session_dir / "flows"
        _atomic_write(flows_dir / f"{issue_id}.json", flow.model_dump_json(indent=2))
        return flow
