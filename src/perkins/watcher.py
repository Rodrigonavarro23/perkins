"""
Watcher components for Perkins.
Governed by: docs/tdrs/perkins-github-operations.md, docs/tdrs/perkins-flow-lifecycle.md
"""
from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from perkins.dispatcher import FlowDispatcher


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


class Watcher:
    """
    Polls GitHub issues via the gh CLI and dispatches new ones to the
    FlowDispatcher. On gh CLI failure, logs to recovery.log and continues
    (per perkins-github-operations TDR — do not crash the daemon).
    """

    def __init__(
        self,
        registry: IssueRegistry,
        dispatcher: FlowDispatcher,
        session_dir: Path,
        github_repo: str,
    ) -> None:
        self._registry = registry
        self._dispatcher = dispatcher
        self._session_dir = session_dir
        self._github_repo = github_repo

    def fetch_open_issues(self) -> list[str]:
        """
        Call gh CLI to list open issues. Returns a list of issue number strings.
        Raises subprocess.CalledProcessError on non-zero exit.
        """
        result = subprocess.run(
            [
                "gh", "issue", "list",
                "--repo", self._github_repo,
                "--json", "number,title,body,labels,state",
                "--state", "open",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        issues = json.loads(result.stdout)
        return [str(issue["number"]) for issue in issues]

    def poll_once(self, active_flows_count: int) -> None:
        """
        Perform a single poll: fetch open issues, dispatch any not yet tracked.
        On gh CLI failure, log to recovery.log and return without crashing.
        """
        try:
            issue_ids = self.fetch_open_issues()
        except subprocess.CalledProcessError as exc:
            self._log_error(
                f"gh CLI failed (exit {exc.returncode}): {exc.stderr.strip() if exc.stderr else 'no stderr'}"
            )
            return

        for issue_id in issue_ids:
            if self._registry.can_dispatch(issue_id):
                self._dispatcher.dispatch(issue_id, self._session_dir, active_flows_count)

    def _log_error(self, message: str) -> None:
        recovery_log = self._session_dir / "recovery.log"
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(recovery_log, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} ERROR {message}\n")
