"""
Unit tests for dev sub-agent lifecycle — covers:
  - Scenario: Master spawns a dev sub-agent for a dispatched issue
  - Scenario: Dev sub-agent completes successfully and opens a PR
  - Scenario: Dev sub-agent exits with non-zero code and awaits human decision
"""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from perkins.agent import (
    create_worktree,
    get_agent_command,
    get_last_n_lines,
    handle_agent_exit,
    set_flow_in_progress,
    spawn_agent,
)
from perkins.config import PerkinsConfig
from perkins.models import FlowState, FlowStatus


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_config(tool: str = "claude-code") -> PerkinsConfig:
    return PerkinsConfig.model_validate({
        "repo": {"name": "test", "description": "d", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "m", "api_key_env": "KEY"},
        "dev_agents": {"default_tool": tool},
    })


def _write_flow(session_dir: Path, issue_id: str, status: FlowStatus) -> None:
    flows_dir = session_dir / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)
    flow = FlowState(issue_id=issue_id, status=status)
    (flows_dir / f"{issue_id}.json").write_text(flow.model_dump_json(indent=2))


def _mock_process(exit_code: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> AsyncMock:
    proc = MagicMock()
    proc.returncode = exit_code
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ── get_agent_command ────────────────────────────────────────────────────────

def test_get_agent_command_claude_code():
    assert get_agent_command("claude-code") == ["claude", "--print"]


def test_get_agent_command_gemini():
    assert get_agent_command("gemini") == ["gemini", "-p"]


def test_get_agent_command_codex():
    assert get_agent_command("codex") == ["codex", "--full-auto"]


# ── create_worktree ──────────────────────────────────────────────────────────

def test_create_worktree_calls_git_with_correct_path(tmp_path):
    with patch("subprocess.run") as mock_run:
        create_worktree("42", worktrees_dir=tmp_path)
    args = mock_run.call_args[0][0]
    assert str(tmp_path / "issue-42") in args


def test_create_worktree_uses_correct_branch_name(tmp_path):
    with patch("subprocess.run") as mock_run:
        create_worktree("42", worktrees_dir=tmp_path)
    args = mock_run.call_args[0][0]
    assert "perkins/issue-42" in args


def test_create_worktree_uses_git_worktree_add(tmp_path):
    with patch("subprocess.run") as mock_run:
        create_worktree("42", worktrees_dir=tmp_path)
    args = mock_run.call_args[0][0]
    assert args[:3] == ["git", "worktree", "add"]


def test_create_worktree_passes_check_true(tmp_path):
    with patch("subprocess.run") as mock_run:
        create_worktree("42", worktrees_dir=tmp_path)
    assert mock_run.call_args[1]["check"] is True


# ── set_flow_in_progress ─────────────────────────────────────────────────────

def test_set_flow_in_progress_updates_status(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)
    set_flow_in_progress(tmp_path, "42")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.status == FlowStatus.in_progress


def test_set_flow_in_progress_leaves_no_tmp_files(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)
    set_flow_in_progress(tmp_path, "42")
    assert list((tmp_path / "flows").glob("*.tmp")) == []


# ── handle_agent_exit — exit code 0 (Scenario: completes successfully) ──────

def test_handle_exit_zero_sets_completed(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    handle_agent_exit(tmp_path, "42", exit_code=0, pr_url="https://github.com/o/r/pull/7")
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.status == FlowStatus.completed


def test_handle_exit_zero_records_pr_url(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    pr_url = "https://github.com/owner/repo/pull/7"
    handle_agent_exit(tmp_path, "42", exit_code=0, pr_url=pr_url)
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.pr_url == pr_url


def test_handle_exit_zero_writes_atomically(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    handle_agent_exit(tmp_path, "42", exit_code=0, pr_url="https://gh.com/pr/1")
    assert list((tmp_path / "flows").glob("*.tmp")) == []


# ── handle_agent_exit — non-zero (Scenario: exits with non-zero code) ────────

def test_handle_exit_nonzero_sets_failed(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    handle_agent_exit(tmp_path, "42", exit_code=1)
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.status == FlowStatus.failed


def test_handle_exit_nonzero_leaves_pr_url_none(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    handle_agent_exit(tmp_path, "42", exit_code=2)
    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    assert flow.pr_url is None


def test_handle_exit_nonzero_writes_atomically(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.in_progress)
    handle_agent_exit(tmp_path, "42", exit_code=1)
    assert list((tmp_path / "flows").glob("*.tmp")) == []


def test_handle_exit_any_nonzero_sets_failed(tmp_path):
    for code in (1, 2, 127, 255):
        _write_flow(tmp_path, str(code), FlowStatus.in_progress)
        handle_agent_exit(tmp_path, str(code), exit_code=code)
        flow = FlowState.model_validate_json(
            (tmp_path / "flows" / f"{code}.json").read_text()
        )
        assert flow.status == FlowStatus.failed


# ── get_last_n_lines (for "perkins status" failure report) ───────────────────

def test_get_last_n_lines_returns_last_n(tmp_path):
    log = tmp_path / "agent.log"
    log.write_text("\n".join(str(i) for i in range(30)))
    lines = get_last_n_lines(log, 20)
    assert len(lines) == 20
    assert lines[-1] == "29"


def test_get_last_n_lines_returns_all_when_fewer_than_n(tmp_path):
    log = tmp_path / "agent.log"
    log.write_text("line1\nline2\nline3")
    assert len(get_last_n_lines(log, 20)) == 3


def test_get_last_n_lines_returns_empty_for_missing_log(tmp_path):
    assert get_last_n_lines(tmp_path / "missing.log", 20) == []


def test_get_last_n_lines_returns_empty_for_empty_log(tmp_path):
    log = tmp_path / "agent.log"
    log.write_text("")
    assert get_last_n_lines(log, 20) == []


# ── spawn_agent (async) ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spawn_agent_sets_flow_to_in_progress(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0, b"output\n", b"")):
        await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    flow = FlowState.model_validate_json((tmp_path / "flows" / "42.json").read_text())
    # spawn_agent sets in_progress (handle_agent_exit is called by the orchestrator separately)
    assert flow.status == FlowStatus.in_progress


@pytest.mark.asyncio
async def test_spawn_agent_creates_agent_log_directory(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0)):
        await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    assert (tmp_path / "flows" / "42").is_dir()


@pytest.mark.asyncio
async def test_spawn_agent_writes_stdout_to_agent_log(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0, b"hello world\n", b"")):
        await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    log = tmp_path / "flows" / "42" / "agent.log"
    assert b"hello world" in log.read_bytes()


@pytest.mark.asyncio
async def test_spawn_agent_writes_stderr_to_agent_log(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0, b"", b"err line\n")):
        await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    log = tmp_path / "flows" / "42" / "agent.log"
    assert b"err line" in log.read_bytes()


@pytest.mark.asyncio
async def test_spawn_agent_uses_correct_command_for_tool(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0)) as mock_exec:
        await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config("claude-code"))

    args = mock_exec.call_args[0]
    assert args[:2] == ("claude", "--print")


@pytest.mark.asyncio
async def test_spawn_agent_uses_worktree_as_cwd(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)
    worktree = Path(".worktrees/issue-42")

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0)) as mock_exec:
        await spawn_agent("42", tmp_path, worktree, _make_config())

    kwargs = mock_exec.call_args[1]
    assert kwargs.get("cwd") == worktree


@pytest.mark.asyncio
async def test_spawn_agent_returns_exit_code_zero(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(0)):
        code = await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    assert code == 0


@pytest.mark.asyncio
async def test_spawn_agent_returns_nonzero_exit_code(tmp_path):
    _write_flow(tmp_path, "42", FlowStatus.dispatched)

    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock,
               return_value=_mock_process(1)):
        code = await spawn_agent("42", tmp_path, Path(".worktrees/issue-42"), _make_config())

    assert code == 1
