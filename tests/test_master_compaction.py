"""
Unit tests for MasterOrchestrator context compaction — covers:
  - Scenario: Context compaction triggers at threshold and stores snapshot
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from perkins.config import PerkinsConfig
from perkins.master import MasterOrchestrator
from perkins.models import FlowState, ProgressEntry


def _make_config(tmp_path: Path) -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "svc", "description": "test repo", "github_repo": "o/r"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "session": {"state_dir": str(tmp_path / ".perkins"), "compaction_threshold": 0.80},
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

    master = MasterOrchestrator(session_id, config, _graph=MagicMock())
    return master, session_dir, flow_path


# ── Snapshot file location ────────────────────────────────────────────────────

def test_compact_context_writes_snapshot_to_compaction_dir(tmp_path):
    """compact_context() writes a file inside .perkins/sessions/{session_id}/compaction/."""
    master, session_dir, _ = _setup(tmp_path)

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())

    assert path.exists()
    assert path.parent == session_dir / "compaction"


def test_compact_context_snapshot_filename(tmp_path):
    """Snapshot filename matches snapshot-{timestamp}.md."""
    master, _, _ = _setup(tmp_path)

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())

    assert path.name.startswith("snapshot-")
    assert path.suffix == ".md"


# ── Snapshot content ──────────────────────────────────────────────────────────

def test_compact_context_snapshot_contains_project_context(tmp_path):
    """Snapshot has a 'Project Context' section with repo name and session ID."""
    master, _, _ = _setup(tmp_path)

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())
    content = path.read_text(encoding="utf-8")

    assert "Project Context" in content
    assert "svc" in content        # repo name
    assert "perk_test01" in content  # session_id


def test_compact_context_snapshot_contains_active_flow_states(tmp_path):
    """Snapshot has an 'Active Flow States' section listing current issue flows."""
    master, _, _ = _setup(tmp_path, issue_id="42")

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())
    content = path.read_text(encoding="utf-8")

    assert "Active Flow States" in content
    assert "42" in content


def test_compact_context_snapshot_contains_pending_escalations(tmp_path):
    """Snapshot has a 'Pending Escalations' section; lists issues with queued interrupts."""
    master, _, _ = _setup(tmp_path)
    # Simulate a pending interrupt
    q: asyncio.Queue = asyncio.Queue()
    q.put_nowait({"type": "ask_master", "question": "Which pattern?"})
    master.interrupt_queues["42"] = q

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())
    content = path.read_text(encoding="utf-8")

    assert "Pending Escalations" in content
    assert "42" in content


def test_compact_context_snapshot_contains_recent_events(tmp_path):
    """Snapshot has a 'Recent Events' section with the latest progress entries."""
    master, _, _ = _setup(
        tmp_path,
        progress_entries=[
            ProgressEntry(timestamp="2026-04-12T10:00:00+00:00", message="All tests passing"),
        ],
    )

    async def _run():
        return await master.compact_context()

    path = asyncio.run(_run())
    content = path.read_text(encoding="utf-8")

    assert "Recent Events" in content
    assert "All tests passing" in content


# ── Compaction trigger ────────────────────────────────────────────────────────

def test_compaction_triggers_when_token_usage_reaches_threshold(tmp_path):
    """compact_context() is called after _ask_master when _should_compact() is True."""
    master, _, _ = _setup(tmp_path)

    # Set token counter to exactly at the threshold
    master._context_tokens = int(master._max_context_tokens * master._config.session.compaction_threshold)

    compact_called: list[bool] = []
    original_compact = master.compact_context

    async def _spy_compact():
        compact_called.append(True)
        return await original_compact()

    master.compact_context = _spy_compact
    master._graph.invoke.return_value = {"answer": "ok"}

    async def _run():
        await master._ask_master("42", "test question", "")

    asyncio.run(_run())

    assert compact_called, "compact_context must be called when threshold is reached"


def test_compaction_does_not_trigger_below_threshold(tmp_path):
    """compact_context() is NOT called when token usage is below the threshold."""
    master, _, _ = _setup(tmp_path)
    master._context_tokens = 0  # well below threshold

    compact_called: list[bool] = []
    original_compact = master.compact_context

    async def _spy_compact():
        compact_called.append(True)
        return await original_compact()

    master.compact_context = _spy_compact
    master._graph.invoke.return_value = {"answer": "ok"}

    async def _run():
        await master._ask_master("42", "test question", "")

    asyncio.run(_run())

    assert not compact_called, "compact_context must NOT be called below threshold"


# ── Context rebuild from snapshot ─────────────────────────────────────────────

def test_context_rebuilt_from_snapshot_on_next_invocation(tmp_path):
    """When a compaction snapshot exists, its content is included in the next graph invocation."""
    master, session_dir, _ = _setup(tmp_path, issue_body="body")

    snap_dir = session_dir / "compaction"
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "snapshot-2026-04-12T10-00-00.md").write_text(
        "# Snapshot\n## Project Context\n- Repo: svc\n",
        encoding="utf-8",
    )

    captured_inputs: list[dict] = []

    def _capture_invoke(input_, config, **kwargs):
        captured_inputs.append(input_)
        return {"answer": "reply"}

    master._graph.invoke.side_effect = _capture_invoke

    async def _run():
        await master._ask_master("42", "What to do?", "")

    asyncio.run(_run())

    assert captured_inputs, "invoke must have been called"
    invoke_input = captured_inputs[0]
    # The snapshot content must be threaded into the invoke input
    combined = " ".join(str(v) for v in invoke_input.values())
    assert "snapshot" in combined.lower() or "Project Context" in combined or "Repo: svc" in combined
