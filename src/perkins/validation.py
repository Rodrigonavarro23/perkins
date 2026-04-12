"""
Startup validation chain for perkins.
Governed by: docs/tdrs/perkins-github-operations.md, docs/tdrs/perkins-cli-framework.md
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class StartupValidationError(Exception):
    """Raised when a startup validation check fails."""


def validate_gh_installed() -> None:
    if shutil.which("gh") is None:
        raise StartupValidationError(
            "GitHub CLI is required. Install from: https://cli.github.com"
        )


def validate_gh_authenticated() -> None:
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise StartupValidationError(
            "GitHub CLI not authenticated. Run: gh auth login"
        )


def validate_cliplin_project() -> None:
    if not Path("cliplin.yaml").exists():
        raise StartupValidationError("No cliplin.yaml found. Run: cliplin init")


def validate_cliplin_acd() -> None:
    knowledge_dir = Path(".cliplin/knowledge")
    if not knowledge_dir.exists():
        raise StartupValidationError(
            "cliplin-acd knowledge package required.\n"
            "Add to cliplin.yaml and run: cliplin knowledge install"
        )
    has_acd = any(
        d.name.startswith("cliplin-acd")
        for d in knowledge_dir.iterdir()
        if d.is_dir()
    )
    if not has_acd:
        raise StartupValidationError(
            "cliplin-acd knowledge package required.\n"
            "Add to cliplin.yaml and run: cliplin knowledge install"
        )


def validate_perkins_yaml() -> None:
    if not Path("perkins.yaml").exists():
        raise StartupValidationError(
            "Run: perkins init to configure perkins for this project"
        )


def validate_api_key(api_key_env: str) -> None:
    import os

    if not os.environ.get(api_key_env):
        raise StartupValidationError(
            f"Required environment variable not set: {api_key_env}"
        )
