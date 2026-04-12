"""
AnswerAgent — posts questions to and polls answers from GitHub issue threads.
Governed by: docs/tdrs/perkins-github-operations.md, docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import json
import subprocess
from typing import Optional


class AnswerAgent:
    """
    Communicates with the human via GitHub issue thread comments.
    Uses gh CLI exclusively (per perkins-github-operations TDR).
    Does not have access to cliplin MCP tools.
    """

    def __init__(self, github_repo: str) -> None:
        self._github_repo = github_repo

    def post_question(self, issue_number: str, question: str) -> None:
        """Post the escalated question as a comment on the GitHub issue thread."""
        subprocess.run(
            [
                "gh", "issue", "comment", issue_number,
                "--repo", self._github_repo,
                "--body", question,
            ],
            check=True,
        )

    def get_latest_comment(self, issue_number: str) -> Optional[str]:
        """
        Return the body of the most recent comment on the issue, or None
        if there are no comments. Called by the polling loop to detect a
        human response after the question was posted.
        """
        result = subprocess.run(
            [
                "gh", "issue", "view", issue_number,
                "--repo", self._github_repo,
                "--json", "comments",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
        comments = data.get("comments", [])
        return comments[-1]["body"] if comments else None
