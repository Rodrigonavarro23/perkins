"""
Unit tests for worktree cleanup — covers:
  - Scenario: Watcher detects closed issue and prompts human before deleting worktree
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from perkins.worktree import WorktreeManager


def _mock_gh_state(state: str) -> MagicMock:
    mock = MagicMock()
    mock.stdout = json.dumps({"state": state})
    return mock


# ── is_issue_closed ──────────────────────────────────────────────────────────

def test_is_issue_closed_returns_true_for_closed():
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=Path("."))
    with patch("subprocess.run", return_value=_mock_gh_state("closed")):
        assert mgr.is_issue_closed("42") is True


def test_is_issue_closed_returns_false_for_open():
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=Path("."))
    with patch("subprocess.run", return_value=_mock_gh_state("open")):
        assert mgr.is_issue_closed("42") is False


def test_is_issue_closed_calls_gh_issue_view():
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=Path("."))
    with patch("subprocess.run", return_value=_mock_gh_state("open")) as mock_run:
        mgr.is_issue_closed("42")
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == ["gh", "issue", "view"]


def test_is_issue_closed_passes_json_state_flag():
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=Path("."))
    with patch("subprocess.run", return_value=_mock_gh_state("closed")) as mock_run:
        mgr.is_issue_closed("42")
    cmd = mock_run.call_args[0][0]
    assert "--json" in cmd and "state" in cmd


# ── prompt_and_cleanup ───────────────────────────────────────────────────────

def test_prompt_text_includes_issue_id(tmp_path, capsys):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run"):
        mgr.prompt_and_cleanup("42", confirm=False)
    output = capsys.readouterr().out
    assert "42" in output


def test_prompt_text_includes_worktree_path(tmp_path, capsys):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run"):
        mgr.prompt_and_cleanup("42", confirm=False)
    output = capsys.readouterr().out
    assert ".worktrees/issue-42" in output


def test_prompt_format_matches_tdr(tmp_path, capsys):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run"):
        mgr.prompt_and_cleanup("42", confirm=False)
    output = capsys.readouterr().out
    assert "Issue #42 is closed" in output


def test_cleanup_calls_git_worktree_remove_when_confirmed(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mgr.prompt_and_cleanup("42", confirm=True)
    cmd = mock_run.call_args[0][0]
    assert cmd[:3] == ["git", "worktree", "remove"]


def test_cleanup_passes_force_flag_when_confirmed(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mgr.prompt_and_cleanup("42", confirm=True)
    cmd = mock_run.call_args[0][0]
    assert "--force" in cmd


def test_cleanup_uses_correct_worktree_path_when_confirmed(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mgr.prompt_and_cleanup("42", confirm=True)
    cmd = mock_run.call_args[0][0]
    assert str(tmp_path / ".worktrees" / "issue-42") in cmd


def test_cleanup_returns_true_when_confirmed(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run"):
        result = mgr.prompt_and_cleanup("42", confirm=True)
    assert result is True


def test_cleanup_does_not_call_git_when_declined(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    with patch("subprocess.run") as mock_run:
        mgr.prompt_and_cleanup("42", confirm=False)
    mock_run.assert_not_called()


def test_cleanup_returns_false_when_declined(tmp_path):
    mgr = WorktreeManager(github_repo="owner/repo", base_dir=tmp_path)
    result = mgr.prompt_and_cleanup("42", confirm=False)
    assert result is False
