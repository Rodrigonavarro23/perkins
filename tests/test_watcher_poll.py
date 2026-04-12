"""
Unit tests for Watcher.poll_once — covers:
  - Scenario: Watcher detects a new GitHub issue and dispatches it to the Master
  - Scenario: Watcher continues polling when gh CLI returns a non-zero exit
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perkins.dispatcher import DispatchQueue, FlowDispatcher
from perkins.models import FlowState, FlowStatus
from perkins.watcher import IssueRegistry, Watcher


def _make_watcher(tmp_path: Path, max_concurrent: int = 5) -> tuple[Watcher, IssueRegistry, DispatchQueue]:
    (tmp_path / "flows").mkdir(parents=True, exist_ok=True)
    registry = IssueRegistry()
    queue = DispatchQueue()
    dispatcher = FlowDispatcher(registry, queue, max_concurrent=max_concurrent)
    watcher = Watcher(
        registry=registry,
        dispatcher=dispatcher,
        session_dir=tmp_path,
        github_repo="owner/repo",
    )
    return watcher, registry, queue


# ── Scenario: Watcher detects a new issue and dispatches it ─────────────────

def test_poll_once_creates_flow_file_for_new_issue(tmp_path):
    watcher, _, _ = _make_watcher(tmp_path)
    with patch.object(watcher, "fetch_open_issues", return_value=["42"]):
        watcher.poll_once(active_flows_count=0)
    assert (tmp_path / "flows" / "42.json").exists()


def test_poll_once_flow_file_has_dispatched_status(tmp_path):
    watcher, _, _ = _make_watcher(tmp_path)
    with patch.object(watcher, "fetch_open_issues", return_value=["42"]):
        watcher.poll_once(active_flows_count=0)
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.status == FlowStatus.dispatched


def test_poll_once_tracks_dispatched_issue_in_registry(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    with patch.object(watcher, "fetch_open_issues", return_value=["42"]):
        watcher.poll_once(active_flows_count=0)
    assert registry.is_tracked("42") is True


def test_poll_once_dispatches_multiple_new_issues(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    with patch.object(watcher, "fetch_open_issues", return_value=["10", "11", "12"]):
        watcher.poll_once(active_flows_count=0)
    assert registry.is_tracked("10")
    assert registry.is_tracked("11")
    assert registry.is_tracked("12")


def test_poll_once_skips_already_tracked_issue(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    registry.track("42")  # already in-flight
    with patch.object(watcher, "fetch_open_issues", return_value=["42"]):
        watcher.poll_once(active_flows_count=0)
    # No new flow file should be created
    assert not (tmp_path / "flows" / "42.json").exists()


def test_poll_once_only_dispatches_new_issues_from_mixed_list(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    registry.track("42")
    with patch.object(watcher, "fetch_open_issues", return_value=["42", "55"]):
        watcher.poll_once(active_flows_count=0)
    assert not (tmp_path / "flows" / "42.json").exists()
    assert (tmp_path / "flows" / "55.json").exists()


# ── Scenario: Watcher continues polling when gh CLI returns non-zero exit ────

def test_poll_once_does_not_raise_on_gh_cli_failure(tmp_path):
    watcher, _, _ = _make_watcher(tmp_path)
    error = subprocess.CalledProcessError(1, "gh", stderr="network error")
    with patch.object(watcher, "fetch_open_issues", side_effect=error):
        watcher.poll_once(active_flows_count=0)  # must not raise


def test_poll_once_logs_gh_cli_failure_to_recovery_log(tmp_path):
    watcher, _, _ = _make_watcher(tmp_path)
    error = subprocess.CalledProcessError(1, "gh", stderr="network error")
    with patch.object(watcher, "fetch_open_issues", side_effect=error):
        watcher.poll_once(active_flows_count=0)
    recovery_log = tmp_path / "recovery.log"
    assert recovery_log.exists()
    content = recovery_log.read_text()
    assert "ERROR" in content


def test_poll_once_creates_no_flows_on_gh_cli_failure(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    error = subprocess.CalledProcessError(1, "gh", stderr="network error")
    with patch.object(watcher, "fetch_open_issues", side_effect=error):
        watcher.poll_once(active_flows_count=0)
    assert list((tmp_path / "flows").glob("*.json")) == []


def test_poll_once_does_not_track_anything_on_gh_cli_failure(tmp_path):
    watcher, registry, _ = _make_watcher(tmp_path)
    error = subprocess.CalledProcessError(1, "gh", stderr="network error")
    with patch.object(watcher, "fetch_open_issues", side_effect=error):
        watcher.poll_once(active_flows_count=0)
    assert not registry.is_tracked("42")


def test_poll_once_recovery_log_appends_on_multiple_failures(tmp_path):
    watcher, _, _ = _make_watcher(tmp_path)
    error = subprocess.CalledProcessError(1, "gh", stderr="timeout")
    with patch.object(watcher, "fetch_open_issues", side_effect=error):
        watcher.poll_once(active_flows_count=0)
        watcher.poll_once(active_flows_count=0)
    content = (tmp_path / "recovery.log").read_text()
    assert content.count("ERROR") == 2


# ── Watcher + DispatchQueue interaction ─────────────────────────────────────

def test_poll_once_queues_issue_when_at_concurrency_limit(tmp_path):
    watcher, registry, queue = _make_watcher(tmp_path, max_concurrent=2)
    with patch.object(watcher, "fetch_open_issues", return_value=["55"]):
        watcher.poll_once(active_flows_count=2)
    flow = FlowState.model_validate_json((tmp_path / "flows" / "55.json").read_text())
    assert flow.status == FlowStatus.queued
    assert queue.is_queued("55") is True
