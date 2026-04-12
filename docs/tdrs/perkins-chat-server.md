---
tdr: "1.0"
id: "perkins-chat-server"
title: "Perkins Chat HTTP Server (IPC bridge for perkins chat)"
summary: "Rules governing the local HTTP server that bridges perkins chat
          (a separate CLI process) with the runtime's in-memory interrupt
          and answer queues."
---

# rules

## HTTP server implementation

- The chat HTTP server MUST be implemented using **aiohttp** (asyncio-native).
- It runs as an asyncio task inside the runtime process, started alongside
  the MCP server, torn down on graceful shutdown.
- The server binds to `0.0.0.0` on a dynamically assigned port (OS-assigned
  via `aiohttp.web.TCPSite` bound to port `0`).
- On startup, the assigned port MUST be written to
  `.perkins/sessions/{session_id}/chat.port` as plain text (integer, no newline).
- On clean shutdown, `chat.port` MUST be deleted.

## Endpoints

### GET /sessions/{session_id}/interrupts

Returns the list of pending interrupt payloads currently on
`interrupt_queues` (non-empty queues only). Does NOT dequeue — it peeks.

Response (200):
```json
[
  { "issue_id": "42", "question": "Which pattern to use?", "context": "..." },
  ...
]
```
Returns `[]` if no pending interrupts.

### POST /sessions/{session_id}/answers/{issue_id}

Delivers the developer's answer to the runtime. Places the answer on
`answer_queues[issue_id]`. Returns 404 if no answer queue exists for that
issue_id (i.e. no in-flight ask_master call).

Request body:
```json
{ "answer": "Use the Repository pattern" }
```
Response (200): `{ "ok": true }`

## perkins chat — client side

- `perkins chat <session_id>` MUST read the port from
  `.perkins/sessions/{session_id}/chat.port`.
- If `chat.port` does not exist → print error "Runtime not running for
  session <session_id>." and exit 1.
- If connection is refused → print error "Could not connect to runtime for
  session <session_id>." and exit 1.
- Uses `asyncio.run()` at the Typer command boundary (per
  perkins-cli-framework.md).
- `--watch` flag: if provided, polls `GET /interrupts` every 2 seconds
  until at least one question is available; then enters the interactive
  answer loop.
- Without `--watch`: fetches once; if empty, prints
  "No pending questions for session <session_id>." and exits 0.

## In-memory only

- The chat server serves only what is currently in `interrupt_queues` and
  `answer_queues` (in-memory asyncio.Queue objects).
- No interrupt or answer state is persisted to disk.
- If the runtime is down, the chat server is unreachable; `perkins chat`
  exits with a connection error.
