---
tdr: "1.0"
id: "perkins-runtime-process"
title: "Perkins Background Runtime Process Launcher"
summary: "Rules governing how the Perkins background runtime is launched from the CLI and how the runtime event loop is structured."
---

# rules

## Background process launcher

- `_start_background_session` in `perkins/cli.py` MUST launch the runtime as a separate OS process using `subprocess.Popen` with `start_new_session=True` and `close_fds=True`.
- The runtime entry point is the module `perkins.runtime`, invoked as `[sys.executable, "-m", "perkins.runtime", session_id, config_path]`.
- The launched process MUST NOT be a daemon — it must survive the CLI process exit.
- The runtime PID MUST be written to `.perkins/sessions/{session-id}/runtime.pid` so that `perkins stop` can terminate it.
- `_start_background_session` MUST return the session ID immediately after launching the process; it MUST NOT wait for the runtime to become ready.

## Runtime entry point (perkins/runtime.py)

- `perkins/runtime.py` is the asyncio runtime entry point. It accepts `session_id` and `config_path` as positional CLI arguments (via `sys.argv`).
- It calls `asyncio.run(runtime_main(session_id, config))` — the only `asyncio.run()` call in the runtime path.
- On startup it writes its own PID to `.perkins/sessions/{session-id}/runtime.pid`.
- It registers `SIGTERM` and `SIGINT` handlers that set a shared `asyncio.Event` (`_shutdown_event`) to initiate graceful shutdown.

## Runtime event loop (runtime_main)

- `runtime_main(session_id, config)` is the top-level coroutine. It MUST start the following components in order:
  1. **MCP server** (stub): log `"perkins-master MCP server started [stub] on port {port}"`.
  2. **Master Orchestrator** (stub): log `"Master Orchestrator started [stub] for session {session_id}"`.
  3. **Watcher polling loop**: `asyncio.create_task(watcher_loop(session_id, config))`.
- `runtime_main` MUST await `_shutdown_event` and then cancel all running tasks before exiting.

## Watcher loop

- `watcher_loop(session_id, config)` is an `async def` coroutine that loops until `_shutdown_event` is set.
- On each iteration it calls `watcher.poll_once()` (already implemented) and then `asyncio.sleep(config.watcher.poll_interval_seconds)`.
- Dispatched issues are forwarded to `FlowDispatcher.dispatch(issue, session_dir)`.
- When an issue is dispatched (not queued), `asyncio.create_task(spawn_agent(...))` is called immediately.

## Stub components

- The MCP server and Master Orchestrator are stubs in this feature. Each logs a startup message and does nothing further.
- Stubs MUST be replaced by real implementations when `mcp` and `deepagents` packages are available (future feature).
- Stubs MUST NOT raise exceptions or prevent the Watcher loop from running.

## Runtime module entry point

- `perkins/runtime.py` MUST include an `if __name__ == "__main__":` block that reads `session_id = sys.argv[1]` and `config_path = Path(sys.argv[2])`, loads the config, and calls `asyncio.run(runtime_main(session_id, config))`.
- This makes the module directly runnable as `python -m perkins.runtime <session_id> <config_path>`.

## Queue drain in watcher_loop

- After each `poll_once()` call, `watcher_loop` MUST drain the `DispatchQueue` up to the available concurrency slots (i.e. `max_concurrent - active_flows_count`).
- For each issue dequeued, it calls `asyncio.create_task(spawn_agent(...))` and updates the flow status to `"in_progress"`.
- This ensures issues queued while the concurrency limit was reached are eventually picked up.

## Graceful shutdown

- On `SIGTERM` or `SIGINT`, `_shutdown_event` is set.
- `runtime_main` awaits all pending `spawn_agent` tasks with a timeout of 5 seconds before exiting.
- The runtime PID file is deleted on clean exit.
- A stale PID file (left by SIGKILL) is out of scope for this feature; `perkins start` does not need to handle it.

## perkins stop — runtime termination

- `stop_session()` MUST read `.perkins/sessions/{session-id}/runtime.pid` and send `SIGTERM` to the runtime process.
- If the PID file does not exist, `stop_session()` logs a warning and returns without error.
- After sending SIGTERM, `stop_session()` waits up to 5 seconds for the process to exit before returning.
