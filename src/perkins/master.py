"""
Master Orchestrator and perkins-master MCP server for Perkins.
Governed by: docs/tdrs/perkins-mcp-server.md, docs/tdrs/perkins-agent-orchestration.md
"""
from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from perkins.config import PerkinsConfig


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

    # ── report_progress (Session 2) ───────────────────────────────────────────

    async def _report_progress(self, issue_id: str, message: str) -> str:
        # Implemented in Session 2
        raise NotImplementedError("report_progress — implemented in Session 2")

    # ── get_task_context (Session 2) ──────────────────────────────────────────

    async def _get_task_context(self, issue_id: str) -> dict:
        # Implemented in Session 2
        raise NotImplementedError("get_task_context — implemented in Session 2")
