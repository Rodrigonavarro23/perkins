"""
perkins init — generates perkins.yaml with placeholder values.
Governed by: docs/tdrs/perkins-cli-framework.md, docs/tdrs/perkins-serialization.md,
             docs/tdrs/perkins-github-operations.md
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

# Placeholder values (documented in perkins-init.feature @constraints.gaps)
PLACEHOLDERS: dict[str, str] = {
    "repo.name": "my-project",
    "repo.description": "A project managed by Perkins",
    "repo.github_repo": "owner/repo",
    "orchestrator.provider": "anthropic",
    "orchestrator.model": "claude-opus-4-6",
    "orchestrator.api_key_env": "ANTHROPIC_API_KEY",
}


def detect_github_repo() -> str:
    """
    Detect 'owner/repo' from git remote origin URL.
    Supports HTTPS (https://github.com/owner/repo.git) and SSH (git@github.com:owner/repo.git).
    Returns the placeholder if detection fails.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = result.stdout.strip()
        if not url:
            return PLACEHOLDERS["repo.github_repo"]

        # HTTPS: https://github.com/owner/repo.git
        match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
        if match:
            return match.group(1)

        return PLACEHOLDERS["repo.github_repo"]
    except subprocess.CalledProcessError:
        return PLACEHOLDERS["repo.github_repo"]


def build_config_dict(existing: dict[str, Any], github_repo: str) -> dict[str, Any]:
    """
    Build a perkins.yaml config dict merging existing valid values with placeholders.

    - Fields present in PerkinsConfig schema are preserved from existing if present.
    - Fields absent from existing are filled with placeholder values.
    - Fields in existing that are NOT in the PerkinsConfig schema are silently dropped.
    """
    existing_repo = existing.get("repo", {}) if isinstance(existing.get("repo"), dict) else {}
    existing_orch = existing.get("orchestrator", {}) if isinstance(existing.get("orchestrator"), dict) else {}

    return {
        "repo": {
            "name": existing_repo.get("name", PLACEHOLDERS["repo.name"]),
            "description": existing_repo.get("description", PLACEHOLDERS["repo.description"]),
            "github_repo": github_repo,
        },
        "orchestrator": {
            "provider": existing_orch.get("provider", PLACEHOLDERS["orchestrator.provider"]),
            "model": existing_orch.get("model", PLACEHOLDERS["orchestrator.model"]),
            "api_key_env": existing_orch.get("api_key_env", PLACEHOLDERS["orchestrator.api_key_env"]),
        },
    }


def run_init(project_dir: Path = Path(".")) -> None:
    """
    Core init logic: detect remote, merge with existing config (if any), write perkins.yaml.
    Separated from the Typer command for testability.
    """
    config_path = project_dir / "perkins.yaml"

    # Load existing config if present
    existing: dict[str, Any] = {}
    if config_path.exists():
        try:
            existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            existing = {}

    # github_repo: preserve if already set to a non-placeholder value; autodetect otherwise
    existing_repo = existing.get("repo", {}) if isinstance(existing.get("repo"), dict) else {}
    existing_github_repo = existing_repo.get("github_repo", PLACEHOLDERS["repo.github_repo"])
    if existing_github_repo == PLACEHOLDERS["repo.github_repo"]:
        github_repo = detect_github_repo()
    else:
        github_repo = existing_github_repo

    config_dict = build_config_dict(existing=existing, github_repo=github_repo)

    config_path.write_text(
        yaml.dump(config_dict, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )

    print(f"perkins.yaml {'updated' if existing else 'created'} at {config_path}")
