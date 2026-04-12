---
tdr: "1.0"
id: "perkins-serialization"
title: "Perkins Configuration and State Serialization"
summary: "Pydantic v2 is the single serialization library for both YAML config and JSON state files."
---

# rules

## Configuration (perkins.yaml)

- `perkins.yaml` MUST be parsed using `PyYAML` as the loader and validated against a **Pydantic v2** model (`PerkinsConfig`).
- If validation fails, the CLI MUST print a human-readable Pydantic validation error and exit with code 1.
- `PerkinsConfig` is the single source of truth for all config keys; no raw dict access to config values in application code.

## State files

- All session and flow state files (`.perkins/sessions/{session-id}/session.json`, `.perkins/sessions/{session-id}/flows/{issue-id}.json`) MUST be serialized using Pydantic v2 `.model_dump_json()` and deserialized using `.model_validate_json()`.
- Each state model MUST define explicit field types; no `Any` or untyped dicts in state models.
- File writes MUST be atomic: write to a `.tmp` file, then rename to the target path to prevent partial writes on crash.
