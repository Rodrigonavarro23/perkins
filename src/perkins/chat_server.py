"""
Perkins Chat HTTP Server — IPC bridge between perkins chat CLI and the runtime.
Governed by: docs/tdrs/perkins-chat-server.md
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from aiohttp import web

if TYPE_CHECKING:
    pass


class ChatServer:
    """
    aiohttp HTTP server that exposes pending interrupt payloads and accepts
    developer answers on behalf of the running MasterOrchestrator.

    Endpoints:
      GET  /sessions/{session_id}/interrupts      → list of pending payloads (peek, no dequeue)
      POST /sessions/{session_id}/answers/{iid}   → deliver answer to answer_queues[iid]
    """

    def __init__(self, session_id: str, session_dir: Path, master: Any) -> None:
        self._session_id = session_id
        self._session_dir = session_dir
        self._master = master
        self._pending: dict[str, dict] = {}
        self._runner: Optional[web.AppRunner] = None
        self._port: Optional[int] = None

    # ── Public registration API (called by MasterOrchestrator) ────────────────

    def register_interrupt(self, issue_id: str, question: str, context: str = "") -> None:
        """Record a pending interrupt so GET /interrupts can surface it."""
        self._pending[issue_id] = {
            "issue_id": issue_id,
            "question": question,
            "context": context,
        }

    def clear_interrupt(self, issue_id: str) -> None:
        """Remove a resolved interrupt from the pending list."""
        self._pending.pop(issue_id, None)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> int:
        """Start the server on a dynamically assigned port. Returns the port."""
        app = web.Application()
        sid = self._session_id
        app.router.add_get(f"/sessions/{sid}/interrupts", self._handle_get_interrupts)
        app.router.add_post(f"/sessions/{sid}/answers/{{issue_id}}", self._handle_post_answer)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", 0)
        await site.start()

        # Retrieve the OS-assigned port
        self._port = site._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

        port_file = self._session_dir / "chat.port"
        port_file.write_text(str(self._port), encoding="utf-8")
        return self._port

    async def stop(self) -> None:
        """Tear down the server and delete the port file."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        port_file = self._session_dir / "chat.port"
        if port_file.exists():
            port_file.unlink()

    # ── Request handlers ──────────────────────────────────────────────────────

    async def _handle_get_interrupts(self, request: web.Request) -> web.Response:
        return web.json_response(list(self._pending.values()))

    async def _handle_post_answer(self, request: web.Request) -> web.Response:
        issue_id = request.match_info["issue_id"]
        if issue_id not in self._master.answer_queues:
            return web.json_response({"error": "no in-flight call for issue"}, status=404)

        data = await request.json()
        answer: str = data["answer"]
        await self._master.answer_queues[issue_id].put(answer)
        self.clear_interrupt(issue_id)
        return web.json_response({"ok": True})
