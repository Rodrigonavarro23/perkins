"""
Unit tests for MasterOrchestrator tool handlers — covers:
  - Scenario: report_progress tool appends entry to flow JSON atomically
  - Scenario: get_task_context returns cached issue body, flow state, and latest compaction snapshot
  - Scenario: get_task_context fetches issue body via gh CLI when not cached
  - Scenario: get_task_context returns partial context when gh CLI fails to fetch issue body
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from perkins.config import PerkinsConfig
from perkins.master import MasterOrchestrator
from perkins.models import FlowState


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "d", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins")},
        "mcp_server": {"port": 7331},
    })


def _setup(tmp_path: Path, issue_id: str = "42", **flow_kwargs):
    """Create session dir, flows dir, and flow JSON. Return (master, session_dir, flow_path)."""
    session_id = "perk_test01"
    config = _make_config(tmp_path)
    state_dir = tmp_path / ".perkins"
    session_dir = state_dir / "sessions" / session_id
    flows_dir = session_dir / "flows"
    flows_dir.mkdir(parents=True)

    flow = FlowState(issue_id=issue_id, **flow_kwargs)
    flow_path = flows_dir / f"{issue_id}.json"
    flow_path.write_text(flow.model_dump_json(indent=2), encoding="utf-8")

    # Pass _graph to bypass real create_deep_agent() — these tests only exercise
    # report_progress and get_task_context, not the graph itself.
    master = MasterOrchestrator(session_id, config, _graph=MagicMock())
    return master, session_dir, flow_path


# ── Scenario: report_progress appends entry atomically ───────────────────────

def test_report_progress_appends_entry_to_progress_entries(tmp_path):
    """A progress entry with timestamp + message is appended to the flow JSON."""
    master, _, flow_path = _setup(tmp_path)

    async def _run():
        await master._report_progress("42", "All tests passing")

    asyncio.run(_run())

    flow = FlowState.model_validate_json(flow_path.read_text(encoding="utf-8"))
    assert len(flow.progress_entries) == 1
    assert flow.progress_entries[0].message == "All tests passing"
    assert flow.progress_entries[0].timestamp  # non-empty ISO-8601 string


def test_report_progress_appends_multiple_entries_in_order(tmp_path):
    """Multiple calls accumulate entries in order."""
    master, _, flow_path = _setup(tmp_path)

    async def _run():
        await master._report_progress("42", "first")
        await master._report_progress("42", "second")

    asyncio.run(_run())

    flow = FlowState.model_validate_json(flow_path.read_text(encoding="utf-8"))
    assert len(flow.progress_entries) == 2
    assert flow.progress_entries[0].message == "first"
    assert flow.progress_entries[1].message == "second"


def test_report_progress_writes_atomically(tmp_path):
    """report_progress writes via a .tmp file then renames (atomic write)."""
    master, _, flow_path = _setup(tmp_path)
    tmp_file = flow_path.with_suffix(".tmp")
    tmp_writes: list[str] = []

    original_rename = __import__("os").rename

    def _spy_rename(src, dst):
        if str(src).endswith(".tmp"):
            tmp_writes.append(Path(src).read_text(encoding="utf-8"))
        original_rename(src, dst)

    async def _run():
        with patch("os.rename", side_effect=_spy_rename):
            await master._report_progress("42", "atomic test")

    asyncio.run(_run())

    assert tmp_writes, "os.rename was never called with a .tmp source"
    entry_data = json.loads(tmp_writes[-1])
    assert any(e["message"] == "atomic test" for e in entry_data["progress_entries"])


# ── Scenario: get_task_context returns cached issue body + flow state + snapshot ──

def test_get_task_context_returns_cached_issue_body(tmp_path):
    """When flow JSON has issue_body, it is returned without calling gh CLI."""
    master, _, _ = _setup(tmp_path, issue_body="This is the issue body")

    result_holder: list[dict] = []

    async def _run():
        with patch("subprocess.run") as mock_run:
            result = await master._get_task_context("42")
            assert not mock_run.called, "gh CLI must not be called when issue_body is cached"
        result_holder.append(result)

    asyncio.run(_run())

    assert result_holder[0]["issue_body"] == "This is the issue body"


def test_get_task_context_returns_flow_state(tmp_path):
    """The returned dict includes the current flow_state from flows/42.json."""
    master, _, _ = _setup(tmp_path, issue_body="body text")

    async def _run():
        return await master._get_task_context("42")

    result = asyncio.run(_run())

    assert "flow_state" in result
    assert result["flow_state"]["issue_id"] == "42"


def test_get_task_context_returns_latest_compaction_snapshot(tmp_path):
    """The most recent snapshot file content is returned as compaction_snapshot."""
    master, session_dir, _ = _setup(tmp_path, issue_body="body")
    snap_dir = session_dir / "compaction"
    snap_dir.mkdir()
    (snap_dir / "snapshot-2026-04-10T10.md").write_text("old snapshot", encoding="utf-8")
    (snap_dir / "snapshot-2026-04-12T10.md").write_text("latest snapshot", encoding="utf-8")
    (snap_dir / "snapshot-2026-04-11T10.md").write_text("middle snapshot", encoding="utf-8")

    async def _run():
        return await master._get_task_context("42")

    result = asyncio.run(_run())

    assert result["compaction_snapshot"] == "latest snapshot"


def test_get_task_context_returns_null_snapshot_when_none_exist(tmp_path):
    """compaction_snapshot is None when the compaction directory is absent."""
    master, _, _ = _setup(tmp_path, issue_body="body")

    async def _run():
        return await master._get_task_context("42")

    result = asyncio.run(_run())

    assert result["compaction_snapshot"] is None


# ── Scenario: get_task_context fetches issue body via gh CLI when not cached ──

def test_get_task_context_calls_gh_cli_when_issue_body_not_cached(tmp_path):
    """When flow JSON has no issue_body, gh CLI is invoked to fetch it."""
    master, _, _ = _setup(tmp_path)  # no issue_body

    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"body": "Fetched body"})

    async def _run():
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            await master._get_task_context("42")
            mock_run.assert_called_once()
            args = mock_run.call_args.args[0]
            assert "gh" in args
            assert "issue" in args
            assert "view" in args
            assert "42" in args

    asyncio.run(_run())


def test_get_task_context_returns_fetched_issue_body(tmp_path):
    """The fetched issue body is returned in the response."""
    master, _, _ = _setup(tmp_path)

    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"body": "Fetched body"})

    async def _run():
        with patch("subprocess.run", return_value=mock_result):
            return await master._get_task_context("42")

    result = asyncio.run(_run())
    assert result["issue_body"] == "Fetched body"


def test_get_task_context_caches_issue_body_in_flow_json(tmp_path):
    """After fetching, the issue_body is written back into the flow JSON."""
    master, _, flow_path = _setup(tmp_path)

    mock_result = MagicMock()
    mock_result.stdout = json.dumps({"body": "Cached body"})

    async def _run():
        with patch("subprocess.run", return_value=mock_result):
            await master._get_task_context("42")

    asyncio.run(_run())

    flow = FlowState.model_validate_json(flow_path.read_text(encoding="utf-8"))
    assert flow.issue_body == "Cached body"


# ── Scenario: get_task_context returns partial context when gh CLI fails ──────

def test_get_task_context_returns_null_issue_body_on_gh_failure(tmp_path):
    """issue_body is None in the response when gh CLI returns non-zero exit."""
    master, _, _ = _setup(tmp_path)  # no issue_body

    async def _run():
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh", stderr="not found")):
            return await master._get_task_context("42")

    result = asyncio.run(_run())
    assert result["issue_body"] is None


def test_get_task_context_does_not_raise_on_gh_failure(tmp_path):
    """MCP server must not propagate exceptions when gh CLI fails."""
    master, _, _ = _setup(tmp_path)

    async def _run():
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh", stderr="err")):
            return await master._get_task_context("42")

    # Must not raise
    result = asyncio.run(_run())
    assert "flow_state" in result


def test_get_task_context_logs_gh_error_to_recovery_log(tmp_path):
    """A gh CLI failure appends an entry to recovery.log."""
    master, session_dir, _ = _setup(tmp_path)

    async def _run():
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "gh", stderr="auth error")):
            await master._get_task_context("42")

    asyncio.run(_run())

    recovery_log = session_dir / "recovery.log"
    assert recovery_log.exists(), "recovery.log must be created on gh failure"
    content = recovery_log.read_text(encoding="utf-8")
    assert "42" in content
    assert "auth error" in content
