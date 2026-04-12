"""
Master Orchestrator and perkins-master MCP server for Perkins.
Governed by: docs/tdrs/perkins-mcp-server.md, docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from mcp.server.fastmcp import FastMCP

from perkins.config import PerkinsConfig
from perkins.models import FlowState, ProgressEntry
from perkins.session import _atomic_write

logger = logging.getLogger(__name__)


class MasterOrchestrator:
    """
    Wraps the deepagents LangGraph Master and the perkins-master MCP server.

    The MCP server exposes three tools to dev sub-agents:
      - ask_master: routes questions through the LangGraph graph; uses interrupt/resume
        when the Master cannot answer from context.
      - report_progress: appends a timestamped entry to the flow JSON (Session 2).
      - get_task_context: returns issue body + flow state + compaction snapshot (Session 2).

    Parameters prefixed with _ are for test injection only.
    """

    def __init__(
        self,
        session_id: str,
        config: PerkinsConfig,
        *,
        _graph: Any = None,
    ) -> None:
        self._session_id = session_id
        self._config = config

        if _graph is None:
            # Wire real LangGraph graph with SqliteSaver checkpointer
            # (perkins-agent-orchestration TDR: SqliteSaver at graph.db, thread_id=session_id)
            db_path = (
                Path(config.session.state_dir)
                / "sessions"
                / session_id
                / "graph.db"
            )
            db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            checkpointer = SqliteSaver(conn)
            checkpointer.setup()
            self._graph = create_deep_agent(
                model=config.orchestrator.model,
                checkpointer=checkpointer,
            )
        else:
            self._graph = _graph

        self.interrupt_queues: dict[str, asyncio.Queue] = {}
        self.answer_queues: dict[str, asyncio.Queue] = {}
        self._mcp: FastMCP | None = None

        # Context compaction state (perkins-agent-orchestration TDR)
        self._context_tokens: int = 0
        self._max_context_tokens: int = 200_000  # Claude 3 context window

    # ── MCP server ────────────────────────────────────────────────────────────

    def _build_mcp(self) -> FastMCP:
        mcp = FastMCP(
            "perkins-master",
            host="0.0.0.0",
            port=self._config.mcp_server.port,
        )

        @mcp.tool()
        async def ask_master(issue_id: str, question: str, context: str = "") -> str:
            return await self._ask_master(issue_id, question, context)

        @mcp.tool()
        async def report_progress(issue_id: str, message: str) -> str:
            return await self._report_progress(issue_id, message)

        @mcp.tool()
        async def get_task_context(issue_id: str) -> dict:
            return await self._get_task_context(issue_id)

        return mcp

    def start(self) -> asyncio.Task:
        """Start the MCP server. Returns the asyncio Task."""
        self._mcp = self._build_mcp()
        return asyncio.create_task(self._mcp.run_sse_async())

    # ── ask_master ────────────────────────────────────────────────────────────

    async def _ask_master(self, issue_id: str, question: str, context: str) -> str:
        """
        Handle ask_master tool call.

        Invokes the LangGraph graph. If the graph answers directly, returns the answer.
        If the graph interrupts (Master cannot answer from context), places the interrupt
        payload on interrupt_queues[issue_id] and awaits an answer on answer_queues[issue_id].
        Once the answer arrives (from perkins chat), resumes the graph and returns the answer.

        Context compaction: before invoking, loads any existing compaction snapshot into the
        context. After invoking, estimates token usage and triggers compaction if the threshold
        is reached (perkins-agent-orchestration TDR).
        """
        graph = self._graph
        if graph is None:
            raise RuntimeError("Master graph not initialized — call set_graph() first")

        # Rebuild context from latest compaction snapshot if one exists
        snapshot = self._load_latest_snapshot()
        if snapshot:
            context = f"[COMPACTION SNAPSHOT]\n{snapshot}\n\n[CURRENT CONTEXT]\n{context}"

        cfg = {"configurable": {"thread_id": self._session_id}}
        result = await asyncio.to_thread(
            graph.invoke,
            {"question": question, "issue_id": issue_id, "context": context},
            cfg,
            version="v2",
        )

        # Accumulate approximate token usage and compact if threshold reached
        answer_text = result.get("answer", "") if isinstance(result, dict) else ""
        self._context_tokens += len(question) + len(context) + len(answer_text)
        if self._should_compact():
            await self.compact_context()

        if "__interrupt__" in result:
            payload = result["__interrupt__"][0].value

            if issue_id not in self.interrupt_queues:
                self.interrupt_queues[issue_id] = asyncio.Queue()
                self.answer_queues[issue_id] = asyncio.Queue()

            await self.interrupt_queues[issue_id].put(payload)
            answer: str = await self.answer_queues[issue_id].get()

            from langgraph.types import Command
            await asyncio.to_thread(
                graph.invoke,
                Command(resume={"answer": answer}),
                cfg,
                version="v2",
            )
            return answer

        return result.get("answer", "")

    # ── context compaction ────────────────────────────────────────────────────

    def _should_compact(self) -> bool:
        """Return True when accumulated token usage has reached the configured threshold."""
        threshold = self._config.session.compaction_threshold
        return self._context_tokens >= int(self._max_context_tokens * threshold)

    def _load_latest_snapshot(self) -> str | None:
        """Return content of the most recent compaction snapshot, or None if absent."""
        session_dir = (
            Path(self._config.session.state_dir)
            / "sessions"
            / self._session_id
        )
        compaction_dir = session_dir / "compaction"
        if not compaction_dir.exists():
            return None
        snapshots = sorted(compaction_dir.glob("snapshot-*.md"))
        if not snapshots:
            return None
        return snapshots[-1].read_text(encoding="utf-8")

    async def compact_context(self) -> Path:
        """
        Write a compaction snapshot summarising current state and return its path.

        Snapshot sections (perkins-agent-orchestration TDR):
          - Project Context
          - Active Flow States
          - Pending Escalations
          - Recent Events

        Resets the token counter so the next compaction cycle starts fresh.
        """
        state_dir = Path(self._config.session.state_dir)
        session_dir = state_dir / "sessions" / self._session_id
        compaction_dir = session_dir / "compaction"
        compaction_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        snapshot_path = compaction_dir / f"snapshot-{timestamp}.md"

        # Collect active flow states
        flows_dir = session_dir / "flows"
        flow_states: list[FlowState] = []
        if flows_dir.exists():
            for fp in sorted(flows_dir.glob("*.json")):
                try:
                    flow_states.append(
                        FlowState.model_validate_json(fp.read_text(encoding="utf-8"))
                    )
                except Exception:
                    pass

        # Collect pending escalations (non-empty interrupt queues)
        pending_escalations: list[str] = [
            f"- Issue #{iid}: pending escalation"
            for iid, q in self.interrupt_queues.items()
            if not q.empty()
        ]

        # Collect recent events from all flow progress entries (last 5 per flow)
        recent_events: list[str] = []
        for flow in flow_states:
            for entry in flow.progress_entries[-5:]:
                recent_events.append(
                    f"- [#{flow.issue_id}] {entry.timestamp}: {entry.message}"
                )

        lines = [
            "# Perkins Compaction Snapshot",
            "",
            "## Project Context",
            f"- Repo: {self._config.repo.name} ({self._config.repo.github_repo})",
            f"- Description: {self._config.repo.description}",
            f"- Session: {self._session_id}",
            "",
            "## Active Flow States",
        ]
        if flow_states:
            for flow in flow_states:
                lines.append(f"- Issue #{flow.issue_id}: {flow.status.value}")
        else:
            lines.append("- (none)")

        lines += ["", "## Pending Escalations"]
        if pending_escalations:
            lines += pending_escalations
        else:
            lines.append("- (none)")

        lines += ["", "## Recent Events"]
        if recent_events:
            lines += recent_events
        else:
            lines.append("- (none)")

        snapshot_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Reset token counter after compaction
        self._context_tokens = 0

        logger.info("Compaction snapshot written to %s", snapshot_path)
        return snapshot_path

    # ── report_progress ───────────────────────────────────────────────────────

    async def _report_progress(self, issue_id: str, message: str) -> str:
        """
        Append a timestamped progress entry to flows/{issue_id}.json.
        Write is atomic via .tmp intermediate file (perkins-serialization TDR).
        """
        state_dir = Path(self._config.session.state_dir)
        session_dir = state_dir / "sessions" / self._session_id
        flow_path = session_dir / "flows" / f"{issue_id}.json"

        flow = FlowState.model_validate_json(flow_path.read_text(encoding="utf-8"))
        flow.progress_entries.append(ProgressEntry(
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            message=message,
        ))
        _atomic_write(flow_path, flow.model_dump_json(indent=2))
        return "ok"

    # ── get_task_context ──────────────────────────────────────────────────────

    async def _get_task_context(self, issue_id: str) -> dict:
        """
        Return {issue_body, flow_state, compaction_snapshot} for the given issue.

        issue_body: read from flow JSON cache; if absent, fetch via gh CLI and cache.
        On gh CLI failure: log to recovery.log, return issue_body=None (server continues).
        compaction_snapshot: content of most recent snapshot-*.md in compaction/; None if absent.
        """
        state_dir = Path(self._config.session.state_dir)
        session_dir = state_dir / "sessions" / self._session_id
        flow_path = session_dir / "flows" / f"{issue_id}.json"

        flow = FlowState.model_validate_json(flow_path.read_text(encoding="utf-8"))

        issue_body = flow.issue_body
        if issue_body is None:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["gh", "issue", "view", issue_id, "--json", "body"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                data = json.loads(result.stdout)
                issue_body = data.get("body", "")
                flow.issue_body = issue_body
                _atomic_write(flow_path, flow.model_dump_json(indent=2))
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.strip() if exc.stderr else ""
                logger.error("gh issue view %s failed: %s", issue_id, stderr)
                _append_to_recovery_log(
                    session_dir,
                    f"gh issue view {issue_id} failed: {stderr}",
                )
                issue_body = None

        # Compaction snapshot: most recent snapshot-*.md (alphabetical sort = chronological)
        compaction_dir = session_dir / "compaction"
        compaction_snapshot: str | None = None
        if compaction_dir.exists():
            snapshots = sorted(compaction_dir.glob("snapshot-*.md"))
            if snapshots:
                compaction_snapshot = snapshots[-1].read_text(encoding="utf-8")

        return {
            "issue_body": issue_body,
            "flow_state": flow.model_dump(),
            "compaction_snapshot": compaction_snapshot,
        }


def _append_to_recovery_log(session_dir: Path, message: str) -> None:
    """Append an error line to recovery.log (perkins-github-operations TDR error handling)."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    recovery_log = session_dir / "recovery.log"
    with open(recovery_log, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} ERROR: {message}\n")
