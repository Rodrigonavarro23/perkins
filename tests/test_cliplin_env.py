"""
Tests for cliplin environment inheritance (batch 1/3).
Covers scenarios:
  - Master loads .mcp.json and passes cliplin-context MCP as mcp_servers
  - Master falls back to interrupt-only mode when .mcp.json is absent
  - Master loads claude-code rules from .claude/rules/ into system prompt
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from perkins.cliplin_env import load_mcp_tools, load_rules


# ── load_rules ──────────────────────────────────────────────────────────────


def test_load_rules_claude_code_returns_concatenated_md(tmp_path):
    rules_dir = tmp_path / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "context.md").write_text("# context rule", encoding="utf-8")
    (rules_dir / "feature-first-flow.md").write_text("# feature flow rule", encoding="utf-8")

    result = load_rules("claude-code", tmp_path)

    assert result is not None
    assert "# context rule" in result
    assert "# feature flow rule" in result


def test_load_rules_claude_code_files_sorted(tmp_path):
    rules_dir = tmp_path / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "b.md").write_text("B", encoding="utf-8")
    (rules_dir / "a.md").write_text("A", encoding="utf-8")

    result = load_rules("claude-code", tmp_path)

    assert result is not None
    assert result.index("A") < result.index("B")


def test_load_rules_missing_dir_returns_none_and_logs(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        result = load_rules("claude-code", tmp_path)

    assert result is None
    assert "not found" in caplog.text


def test_load_rules_gemini(tmp_path):
    rules_dir = tmp_path / ".gemini"
    rules_dir.mkdir()
    (rules_dir / "rules.md").write_text("gemini rule", encoding="utf-8")

    result = load_rules("gemini", tmp_path)

    assert result == "gemini rule"


def test_load_rules_cursor_uses_mdc_files(tmp_path):
    rules_dir = tmp_path / ".cursor" / "rules"
    rules_dir.mkdir(parents=True)
    (rules_dir / "rules.mdc").write_text("cursor rule", encoding="utf-8")

    result = load_rules("cursor", tmp_path)

    assert result == "cursor rule"


def test_load_rules_cursor_falls_back_to_cursorrules(tmp_path):
    (tmp_path / ".cursorrules").write_text("legacy cursor rule", encoding="utf-8")

    result = load_rules("cursor", tmp_path)

    assert result == "legacy cursor rule"


def test_load_rules_cursor_both_absent_returns_none(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        result = load_rules("cursor", tmp_path)

    assert result is None


def test_load_rules_unknown_tool_returns_none(tmp_path, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        result = load_rules("unknown-tool", tmp_path)

    assert result is None


# ── load_mcp_tools ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_load_mcp_tools_absent_returns_empty_and_logs(tmp_path, caplog):
    import logging
    mcp_path = tmp_path / ".mcp.json"

    with caplog.at_level(logging.WARNING):
        result = await load_mcp_tools(mcp_path)

    assert result == []
    assert "not found" in caplog.text
    assert "escalate" in caplog.text


@pytest.mark.asyncio
async def test_load_mcp_tools_malformed_json_returns_empty_and_logs(tmp_path, caplog):
    import logging
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text("not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = await load_mcp_tools(mcp_path)

    assert result == []
    assert "malformed" in caplog.text


@pytest.mark.asyncio
async def test_load_mcp_tools_empty_servers_returns_empty(tmp_path, caplog):
    import logging
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = await load_mcp_tools(mcp_path)

    assert result == []


@pytest.mark.asyncio
async def test_load_mcp_tools_calls_client_with_stdio_connections(tmp_path):
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {
            "cliplin-context": {
                "command": "uv",
                "args": ["run", "cliplin", "mcp"],
            }
        }
    }), encoding="utf-8")

    fake_tool = MagicMock()
    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(return_value=[fake_tool])

    with patch("perkins.cliplin_env.MultiServerMCPClient", return_value=mock_client) as MockClient:
        result = await load_mcp_tools(mcp_path)

    # Client was instantiated with correct StdioConnection
    call_kwargs = MockClient.call_args.kwargs
    connections = call_kwargs["connections"]
    assert "cliplin-context" in connections
    assert connections["cliplin-context"]["command"] == "uv"
    assert connections["cliplin-context"]["args"] == ["run", "cliplin", "mcp"]
    assert connections["cliplin-context"]["transport"] == "stdio"

    assert result == [fake_tool]


@pytest.mark.asyncio
async def test_load_mcp_tools_client_failure_returns_empty_and_logs(tmp_path, caplog):
    import logging
    mcp_path = tmp_path / ".mcp.json"
    mcp_path.write_text(json.dumps({
        "mcpServers": {"cliplin-context": {"command": "uv", "args": []}}
    }), encoding="utf-8")

    mock_client = MagicMock()
    mock_client.get_tools = AsyncMock(side_effect=RuntimeError("connection refused"))

    with patch("perkins.cliplin_env.MultiServerMCPClient", return_value=mock_client):
        with caplog.at_level(logging.WARNING):
            result = await load_mcp_tools(mcp_path)

    assert result == []
    assert "Failed to load MCP tools" in caplog.text


# ── MasterOrchestrator.initialize() ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_initialize_passes_mcp_tools_and_rules_to_create_deep_agent(tmp_path):
    """Scenario: Master loads .mcp.json and claude-code rules; both reach create_deep_agent."""
    from perkins.config import PerkinsConfig
    from perkins.master import MasterOrchestrator

    config = PerkinsConfig.model_validate({
        "repo": {"name": "test", "description": "test repo", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_key_env": "ANTHROPIC_API_KEY"},
        "dev_agents": {"default_tool": "claude-code"},
    })

    fake_tool = MagicMock()
    fake_graph = MagicMock()

    with patch("perkins.master.load_mcp_tools", new=AsyncMock(return_value=[fake_tool])) as mock_mcp, \
         patch("perkins.master.load_rules", return_value="# rules content") as mock_rules, \
         patch("perkins.master.create_deep_agent", return_value=fake_graph) as mock_agent, \
         patch("perkins.master.SqliteSaver"):

        master = MasterOrchestrator("perk_abc123", config)
        await master.initialize(project_root=tmp_path)

    mock_mcp.assert_awaited_once_with(tmp_path / ".mcp.json")
    mock_rules.assert_called_once_with("claude-code", tmp_path)
    call_kwargs = mock_agent.call_args.kwargs
    assert call_kwargs["tools"] == [fake_tool]
    assert call_kwargs["system_prompt"] == "# rules content"
    assert master._graph is fake_graph


@pytest.mark.asyncio
async def test_initialize_with_no_mcp_json_succeeds_without_tools(tmp_path):
    """Scenario: Master falls back to interrupt-only mode when .mcp.json is absent."""
    from perkins.config import PerkinsConfig
    from perkins.master import MasterOrchestrator

    config = PerkinsConfig.model_validate({
        "repo": {"name": "test", "description": "test repo", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_key_env": "ANTHROPIC_API_KEY"},
        "dev_agents": {"default_tool": "claude-code"},
    })

    fake_graph = MagicMock()

    with patch("perkins.master.load_mcp_tools", new=AsyncMock(return_value=[])), \
         patch("perkins.master.load_rules", return_value=None), \
         patch("perkins.master.create_deep_agent", return_value=fake_graph) as mock_agent, \
         patch("perkins.master.SqliteSaver"):

        master = MasterOrchestrator("perk_abc123", config)
        await master.initialize(project_root=tmp_path)

    call_kwargs = mock_agent.call_args.kwargs
    assert call_kwargs.get("tools") in ([], None)
    assert call_kwargs.get("system_prompt") is None
    assert master._graph is fake_graph


@pytest.mark.asyncio
async def test_initialize_skips_when_graph_already_injected(tmp_path):
    """Test injection: if _graph is pre-set, initialize() is a no-op."""
    from perkins.config import PerkinsConfig
    from perkins.master import MasterOrchestrator

    config = PerkinsConfig.model_validate({
        "repo": {"name": "test", "description": "test repo", "github_repo": "owner/repo"},
        "orchestrator": {"provider": "anthropic", "model": "claude-sonnet-4-6", "api_key_env": "ANTHROPIC_API_KEY"},
        "dev_agents": {"default_tool": "claude-code"},
    })
    injected_graph = MagicMock()

    with patch("perkins.master.load_mcp_tools", new=AsyncMock()) as mock_mcp:
        master = MasterOrchestrator("perk_abc123", config, _graph=injected_graph)
        await master.initialize(project_root=tmp_path)

    mock_mcp.assert_not_awaited()
    assert master._graph is injected_graph
