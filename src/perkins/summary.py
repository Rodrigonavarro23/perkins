"""
Project context summary builder for perkins summary.
Governed by: docs/tdrs/perkins-cli-framework.md, docs/tdrs/perkins-serialization.md
"""
from __future__ import annotations

from perkins.config import PerkinsConfig


def build_summary_text(config: PerkinsConfig, context: dict) -> str:
    """
    Produce a human-readable project context snapshot from perkins.yaml config
    and context loaded from the cliplin context store.
    """
    lines: list[str] = [
        f"# {config.repo.name}",
        config.repo.description,
        "",
        "## Technology Stack",
        context.get("stack", "Unknown"),
        "",
        "## Key Responsibilities",
    ]
    for responsibility in context.get("responsibilities", []):
        lines.append(f"- {responsibility}")

    lines += ["", "## Key Decisions"]
    for decision in context.get("key_decisions", []):
        summary = decision.get("summary", "")
        source = decision.get("source", "")
        lines.append(f"- {summary} ({source})")

    return "\n".join(lines)


def build_summary_json(config: PerkinsConfig, context: dict) -> dict:
    """
    Produce a machine-readable project description for perkins summary --json.
    Keys: repo, stack, responsibilities, key_decisions (each with source reference).
    """
    return {
        "repo": {
            "name": config.repo.name,
            "description": config.repo.description,
            "github_repo": config.repo.github_repo,
        },
        "stack": context.get("stack", ""),
        "responsibilities": context.get("responsibilities", []),
        "key_decisions": context.get("key_decisions", []),
    }
