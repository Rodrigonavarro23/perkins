"""
Session lifecycle management for Perkins.
Governed by: docs/tdrs/perkins-serialization.md, docs/tdrs/perkins-flow-lifecycle.md,
             docs/tdrs/perkins-runtime-process.md
"""
from __future__ import annotations

import logging
import os
import secrets
import signal
from pathlib import Path

from perkins.config import PerkinsConfig
from perkins.models import SessionState, SessionStatus

logger = logging.getLogger(__name__)


def generate_session_id() -> str:
    """Return a new unique session ID in the format perk_[a-f0-9]{6}."""
    return "perk_" + secrets.token_hex(3)


def _atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via a .tmp intermediate file."""
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.rename(tmp_path, path)


def start_session(config: PerkinsConfig) -> str:
    """
    Create the session directory structure and write an initial session.json.
    Returns the new session ID.
    """
    session_id = generate_session_id()
    state_dir = Path(config.session.state_dir)
    session_dir = state_dir / "sessions" / session_id
    flows_dir = session_dir / "flows"
    flows_dir.mkdir(parents=True, exist_ok=True)

    state = SessionState(session_id=session_id)
    _atomic_write(session_dir / "session.json", state.model_dump_json(indent=2))

    return session_id


def stop_session(session_id: str, config: PerkinsConfig) -> None:
    """
    Gracefully stop a session: send SIGTERM to the runtime process (if running),
    wait up to 5 seconds for it to exit, then update session status to completed.
    """
    state_dir = Path(config.session.state_dir)
    session_dir = state_dir / "sessions" / session_id
    session_file = session_dir / "session.json"

    # Send SIGTERM to the runtime process via PID file
    pid_file = session_dir / "runtime.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        os.kill(pid, signal.SIGTERM)
        os.waitpid(pid, 0)
    else:
        logger.warning("runtime.pid not found for session %s — runtime may have already exited", session_id)

    state = SessionState.model_validate_json(session_file.read_text(encoding="utf-8"))
    state.status = SessionStatus.completed
    _atomic_write(session_file, state.model_dump_json(indent=2))
