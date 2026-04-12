---
tdr: "1.0"
id: "perkins-cli-framework"
title: "Perkins CLI Framework"
summary: "Typer is the CLI framework for all perkins commands."
---

# rules

## CLI framework

- All `perkins` CLI commands MUST be implemented using **Typer**.
- Each top-level command (`start`, `stop`, `chat`, `status`, `flow`, `init`, `summary`) is a Typer `@app.command()`.
- Sub-commands with options (e.g. `perkins status <session-id>`, `perkins summary --json`) use Typer's argument and option decorators.
- The entry point is `perkins.cli:main`, registered in `pyproject.toml` under `[project.scripts]`.
- Typer's `rich` integration (via `rich-click`) is enabled for formatted help output.
- Long-running commands (`perkins start`, `perkins chat`) MUST use `asyncio.run()` at the Typer command boundary to bridge into the async runtime.
