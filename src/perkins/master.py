"""
Master Orchestrator and perkins-master MCP server for Perkins.
Governed by: docs/tdrs/perkins-mcp-server.md, docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

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
        self._graph = _graph  # injected in tests; real graph wired in Session 3
        self.interrupt_queues: dict[str, asyncio.Queue] = {}
        self.answer_queues: dict[str, asyncio.Queue] = {}
        self._mcp: FastMCP | None = None

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
        """
        graph = self._graph
        if graph is None:
            raise RuntimeError("Master graph not initialized — call set_graph() first")

        cfg = {"configurable": {"thread_id": self._session_id}}
        result = await asyncio.to_thread(
            graph.invoke,
            {"question": question, "issue_id": issue_id, "context": context},
            cfg,
        )

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
            )
            return answer

        return result.get("answer", "")

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
