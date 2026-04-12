"""
Watcher components for Perkins.
Governed by: docs/tdrs/perkins-github-operations.md, docs/tdrs/perkins-flow-lifecycle.md
"""
from __future__ import annotations


class IssueRegistry:
    """
    In-memory registry of issues that are already being processed.
    Prevents the Watcher from dispatching the same issue twice.
    """

    def __init__(self) -> None:
        self._tracked: set[str] = set()

    def track(self, issue_id: str) -> None:
        """Mark an issue as tracked (in-flight)."""
        self._tracked.add(issue_id)

    def is_tracked(self, issue_id: str) -> bool:
        """Return True if the issue is already in the active flow registry."""
        return issue_id in self._tracked

    def can_dispatch(self, issue_id: str) -> bool:
        """Return True if the issue may be dispatched (not already tracked)."""
        return issue_id not in self._tracked
