"""
Cliplin environment inheritance for the Master Orchestrator.
Governed by: docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StdioConnection

logger = logging.getLogger(__name__)

_RULES_DIR_MAP: dict[str, tuple[str, str]] = {
    "claude-code": (".claude/rules", "*.md"),
    "gemini": (".gemini", "*.md"),
    "cursor": (".cursor/rules", "*.mdc"),
}
_CURSOR_LEGACY = ".cursorrules"


def load_rules(tool: str, project_root: Path = Path(".")) -> str | None:
    """
    Load and concatenate rule files for the configured AI tool.
    Returns None if no rules source exists (warning logged).
    """
    if tool not in _RULES_DIR_MAP:
        logger.warning("Unknown dev tool %r — skipping rules load", tool)
        return None

    rules_dir_rel, glob_pattern = _RULES_DIR_MAP[tool]
    rules_dir = project_root / rules_dir_rel

    # cursor: prefer .cursor/rules/*.mdc; fall back to .cursorrules
    if tool == "cursor" and not rules_dir.exists():
        legacy = project_root / _CURSOR_LEGACY
        if legacy.exists():
            return legacy.read_text(encoding="utf-8")
        logger.warning(
            "cursor rules: neither %s nor %s found — initializing without rules",
            rules_dir,
            legacy,
        )
        return None

    if not rules_dir.exists():
        logger.warning(
            "%s rules directory %s not found — initializing without rules",
            tool,
            rules_dir,
        )
        return None

    files = sorted(rules_dir.glob(glob_pattern))
    if not files:
        logger.warning("%s rules directory %s is empty", tool, rules_dir)
        return None

    return "\n\n".join(f.read_text(encoding="utf-8") for f in files)


async def load_mcp_tools(mcp_json_path: Path) -> list[BaseTool]:
    """
    Read .mcp.json and return LangChain BaseTool instances via MultiServerMCPClient.
    Returns [] with a warning if the file is absent, malformed, or the client fails.
    """
    if not mcp_json_path.exists():
        logger.warning(
            "%s not found — cliplin-context MCP unavailable, "
            "Master will escalate all unknown questions to human",
            mcp_json_path,
        )
        return []

    try:
        data = json.loads(mcp_json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(
            "%s malformed (%s) — cliplin-context MCP unavailable, "
            "Master will escalate all unknown questions to human",
            mcp_json_path,
            exc,
        )
        return []

    servers: dict = data.get("mcpServers", {})
    if not servers:
        logger.warning("No mcpServers entries in %s — no MCP tools loaded", mcp_json_path)
        return []

    connections: dict[str, StdioConnection] = {
        name: StdioConnection(
            transport="stdio",
            command=cfg["command"],
            args=cfg.get("args", []),
        )
        for name, cfg in servers.items()
    }

    try:
        client = MultiServerMCPClient(connections=connections)
        return await client.get_tools()
    except Exception as exc:
        logger.warning(
            "Failed to load MCP tools from %s (%s) — initializing without MCP tools",
            mcp_json_path,
            exc,
        )
        return []
