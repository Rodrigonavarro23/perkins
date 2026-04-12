"""
Unit tests for AnswerAgent GitHub thread communication — covers:
  - Scenario: Master escalates an unanswerable question to the human via the issue thread
  - Scenario: Human responds on the issue thread and Master resumes the dev sub-agent
"""
import json
from unittest.mock import MagicMock, patch

from perkins.answer_agent import AnswerAgent


# ── post_question (Scenario: Answer Agent posts to GitHub issue thread) ──────

def test_post_question_calls_gh_issue_comment():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run") as mock_run:
        agent.post_question("38", "What auth scheme should I use?")
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[:3] == ["gh", "issue", "comment"]


def test_post_question_passes_issue_number():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run") as mock_run:
        agent.post_question("38", "What auth scheme?")
    called_cmd = mock_run.call_args[0][0]
    assert "38" in called_cmd


def test_post_question_passes_body():
    question = "What auth scheme should I use?"
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run") as mock_run:
        agent.post_question("38", question)
    called_cmd = mock_run.call_args[0][0]
    assert question in called_cmd


def test_post_question_passes_repo():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run") as mock_run:
        agent.post_question("38", "Q?")
    called_cmd = mock_run.call_args[0][0]
    assert "owner/repo" in called_cmd


def test_post_question_passes_check_true():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run") as mock_run:
        agent.post_question("38", "Q?")
    assert mock_run.call_args[1]["check"] is True


# ── get_latest_comment (Scenario: Answer Agent polls for human response) ─────

def _mock_gh_view(comments: list[dict]) -> MagicMock:
    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"comments": comments})
    return mock_result


def test_get_latest_comment_calls_gh_issue_view():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view([])) as mock_run:
        agent.get_latest_comment("38")
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[:3] == ["gh", "issue", "view"]


def test_get_latest_comment_passes_json_flag():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view([])) as mock_run:
        agent.get_latest_comment("38")
    called_cmd = mock_run.call_args[0][0]
    assert "--json" in called_cmd
    assert "comments" in called_cmd


def test_get_latest_comment_passes_repo():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view([])) as mock_run:
        agent.get_latest_comment("38")
    called_cmd = mock_run.call_args[0][0]
    assert "owner/repo" in called_cmd


def test_get_latest_comment_returns_none_when_no_comments():
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view([])):
        result = agent.get_latest_comment("38")
    assert result is None


def test_get_latest_comment_returns_latest_body():
    comments = [
        {"body": "Bot question: what auth?"},
        {"body": "Use JWT."},
    ]
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view(comments)):
        result = agent.get_latest_comment("38")
    assert result == "Use JWT."


def test_get_latest_comment_returns_single_comment_body():
    comments = [{"body": "Please clarify the scope."}]
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view(comments)):
        result = agent.get_latest_comment("38")
    assert result == "Please clarify the scope."


def test_get_latest_comment_returns_last_of_multiple():
    comments = [
        {"body": "first"},
        {"body": "second"},
        {"body": "third"},
    ]
    agent = AnswerAgent(github_repo="owner/repo")
    with patch("subprocess.run", return_value=_mock_gh_view(comments)):
        result = agent.get_latest_comment("38")
    assert result == "third"
