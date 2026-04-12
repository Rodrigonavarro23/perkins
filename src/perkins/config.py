"""
PerkinsConfig — Pydantic v2 model for perkins.yaml.
Governed by: docs/tdrs/perkins-serialization.md, docs/tdrs/perkins-flow-lifecycle.md
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RepoConfig(BaseModel):
    name: str
    description: str
    github_repo: str


class OrchestratorConfig(BaseModel):
    provider: str
    model: str
    api_key_env: str


class DevAgentsConfig(BaseModel):
    default_tool: Literal["claude-code", "gemini", "codex"] = "claude-code"
    max_concurrent: int = Field(default=5, ge=1)
    cleanup_worktree_on: Literal["issue_closed", "session_stop", "manual"] = "issue_closed"


class WatcherConfig(BaseModel):
    poll_interval_seconds: int = Field(default=30, ge=1)
    source: Literal["github-issues", "github-project"] = "github-issues"
    label_filter: str | None = None


class MCPServerConfig(BaseModel):
    port: int = Field(default=7331, ge=1, le=65535)


class SessionConfig(BaseModel):
    state_dir: str = ".perkins"
    compaction_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    max_snapshots_per_session: int = Field(default=10, ge=1)


class TokenOptimizationConfig(BaseModel):
    rtk_enabled: bool = True


class PerkinsConfig(BaseModel):
    repo: RepoConfig
    orchestrator: OrchestratorConfig
    dev_agents: DevAgentsConfig = Field(default_factory=DevAgentsConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    mcp_server: MCPServerConfig = Field(default_factory=MCPServerConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    token_optimization: TokenOptimizationConfig = Field(default_factory=TokenOptimizationConfig)
