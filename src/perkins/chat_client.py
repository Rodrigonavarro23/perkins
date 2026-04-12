"""
Perkins Chat CLI client — connects to the runtime chat HTTP server,
presents pending questions, and delivers developer answers.
Governed by: docs/tdrs/perkins-chat-server.md, docs/tdrs/perkins-cli-framework.md
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp
import typer


async def run_chat(
    session_id: str,
    watch: bool = False,
    state_dir: Path = Path(".perkins"),
) -> None:
    """
    Main async entrypoint for `perkins chat <session_id>`.

    Reads the port from .perkins/sessions/{session_id}/chat.port, connects to
    the chat HTTP server, and enters the interactive question/answer loop.
    """
    port_file = state_dir / "sessions" / session_id / "chat.port"

    if not port_file.exists():
        typer.echo(f"Runtime not running for session {session_id}.")
        raise typer.Exit(1)

    port = int(port_file.read_text(encoding="utf-8").strip())
    base_url = f"http://127.0.0.1:{port}"
    interrupts_url = f"{base_url}/sessions/{session_id}/interrupts"

    try:
        async with aiohttp.ClientSession() as http:
            interrupts = await _get_interrupts(http, interrupts_url)

            if not interrupts and not watch:
                typer.echo(f"No pending questions for session {session_id}.")
                return

            if watch:
                while not interrupts:
                    await asyncio.sleep(2)
                    interrupts = await _get_interrupts(http, interrupts_url)

            for item in interrupts:
                issue_id = item["issue_id"]
                question = item["question"]
                typer.echo(f"\n[Issue #{issue_id}] {question}")
                answer = input("Your answer: ")
                answer_url = f"{base_url}/sessions/{session_id}/answers/{issue_id}"
                await _post_answer(http, answer_url, answer)
                typer.echo(f"Answer delivered for issue #{issue_id}.")

    except aiohttp.ClientConnectorError:
        typer.echo(f"Could not connect to runtime for session {session_id}.")
        raise typer.Exit(1)


async def _get_interrupts(http: aiohttp.ClientSession, url: str) -> list[dict]:
    async with http.get(url) as resp:
        return await resp.json()


async def _post_answer(http: aiohttp.ClientSession, url: str, answer: str) -> None:
    async with http.post(url, json={"answer": answer}) as resp:
        await resp.json()
