"""
Perkins CLI entry point.
Governed by: docs/tdrs/perkins-cli-framework.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError

from perkins.config import PerkinsConfig
from perkins.init import run_init
from perkins.runtime_launcher import start_background_session
from perkins.session import stop_session
from perkins.validation import (
    StartupValidationError,
    validate_cliplin_acd,
    validate_cliplin_project,
    validate_gh_authenticated,
    validate_gh_installed,
    validate_perkins_yaml,
    validate_api_key,
)

app = typer.Typer(
    name="perkins",
    help="Autonomous multi-agent development system.",
    rich_markup_mode="rich",
)


def _load_config(path: Path) -> PerkinsConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return PerkinsConfig.model_validate(data)


def _start_background_session(config: PerkinsConfig) -> str:
    """
    Launch the asyncio runtime as a detached subprocess and return the session ID.
    Governed by: docs/tdrs/perkins-runtime-process.md
    """
    return start_background_session(config, config_path=Path("perkins.yaml"))


@app.command()
def start(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed without starting."),
) -> None:
    """Start a Perkins session. Returns a session ID immediately."""
    try:
        validate_gh_installed()
        validate_gh_authenticated()
        validate_cliplin_project()
        validate_cliplin_acd()
        validate_perkins_yaml()
    except StartupValidationError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    config_path = Path("perkins.yaml")
    try:
        config = _load_config(config_path)
    except ValidationError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    try:
        validate_api_key(config.orchestrator.api_key_env)
    except StartupValidationError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    if dry_run:
        typer.echo("Dry run — no session started.")
        return

    session_id = _start_background_session(config)
    typer.echo(f"Perkins session started.")
    typer.echo(f"SESSION_ID: {session_id}")
    typer.echo(f"Attach with: perkins chat {session_id}")


@app.command()
def stop(
    session_id: str = typer.Argument(..., help="Session ID to stop."),
) -> None:
    """Stop a running Perkins session gracefully."""
    config_path = Path("perkins.yaml")
    try:
        config = _load_config(config_path)
    except ValidationError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    stop_session(session_id, config)
    typer.echo(f"Session {session_id} stopped.")


@app.command()
def chat(
    session_id: str = typer.Argument(..., help="Session ID to attach to."),
    watch: bool = typer.Option(False, "--watch", help="Poll until a question is available."),
) -> None:
    """Open an interactive chat with a running Perkins session."""
    import asyncio
    from perkins.chat_client import run_chat
    asyncio.run(run_chat(session_id, watch=watch))


@app.command()
def status(
    session_id: Optional[str] = typer.Argument(None, help="Session ID for detailed view."),
) -> None:
    """List running sessions and their active flows."""
    raise NotImplementedError("Not yet implemented")


@app.command()
def flow(
    session_id: str = typer.Argument(..., help="Session ID."),
    issue_id: str = typer.Argument(..., help="Issue ID to inspect."),
) -> None:
    """Inspect a specific flow inside a session."""
    raise NotImplementedError("Not yet implemented")


@app.command()
def init() -> None:
    """Configure Perkins for this project (run once per project)."""
    try:
        validate_gh_installed()
        validate_gh_authenticated()
        validate_cliplin_project()
        validate_cliplin_acd()
    except StartupValidationError as e:
        typer.echo(str(e))
        raise typer.Exit(1)

    run_init()


@app.command()
def summary(
    json: bool = typer.Option(False, "--json", help="Machine-readable output."),
    session: Optional[str] = typer.Option(None, "--session", help="Scope to a specific session."),
) -> None:
    """Show a structured project context snapshot."""
    raise NotImplementedError("Not yet implemented")


def main() -> None:
    app()
