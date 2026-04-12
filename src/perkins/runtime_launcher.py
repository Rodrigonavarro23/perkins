"""
Background runtime process launcher for Perkins.
Governed by: docs/tdrs/perkins-runtime-process.md, docs/tdrs/perkins-cli-framework.md
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from perkins.config import PerkinsConfig
from perkins.session import start_session


def start_background_session(config: PerkinsConfig, config_path: Path) -> str:
    """
    Create the session directory structure, launch the asyncio runtime as a
    detached subprocess, write its PID, and return the session ID immediately.

    The runtime is launched via:
        sys.executable -m perkins.runtime <session_id> <config_path>
    with start_new_session=True so it survives the CLI process exit.
    """
    session_id = start_session(config)
    state_dir = Path(config.session.state_dir)
    session_dir = state_dir / "sessions" / session_id

    cmd = [sys.executable, "-m", "perkins.runtime", session_id, str(config_path)]
    try:
        proc = subprocess.Popen(
            cmd,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        raise RuntimeError(f"Failed to launch perkins runtime: {exc}") from exc

    pid_file = session_dir / "runtime.pid"
    pid_file.write_text(str(proc.pid), encoding="utf-8")

    return session_id
