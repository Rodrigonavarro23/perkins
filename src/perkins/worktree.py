"""
Worktree lifecycle management for Perkins.
Governed by: docs/tdrs/perkins-flow-lifecycle.md, docs/tdrs/perkins-github-operations.md
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


class WorktreeManager:
    """
    Checks issue state via gh CLI and manages git worktree cleanup
    with mandatory human confirmation (per perkins-flow-lifecycle TDR).
    """

    def __init__(self, github_repo: str, base_dir: Path) -> None:
        self._github_repo = github_repo
        self._base_dir = base_dir

    def is_issue_closed(self, issue_number: str) -> bool:
        """Return True if the GitHub issue is in 'closed' state."""
        result = subprocess.run(
            [
                "gh", "issue", "view", issue_number,
                "--repo", self._github_repo,
                "--json", "state",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        return data.get("state", "").lower() == "closed"

    def prompt_and_cleanup(self, issue_id: str, confirm: bool) -> bool:
        """
        Print the TDR-mandated prompt and remove the worktree if confirmed.

        The `confirm` parameter is the pre-resolved human decision (True = yes).
        In production this is provided by the CLI after printing the prompt and
        reading stdin; in tests it is injected directly.

        Returns True if the worktree was removed, False otherwise.
        """
        worktree_path = self._base_dir / ".worktrees" / f"issue-{issue_id}"
        print(
            f"Issue #{issue_id} is closed. "
            f"Delete worktree at .worktrees/issue-{issue_id}/? [y/N]"
        )
        if confirm:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                check=True,
            )
            return True
        return False
