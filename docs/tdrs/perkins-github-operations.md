---
tdr: "1.0"
id: "perkins-github-operations"
title: "GitHub Operations via gh CLI"
summary: "All GitHub operations use the gh CLI via subprocess; no Python GitHub API client."
---

# rules

## Interface

- All GitHub operations (issue listing, issue commenting, PR creation) MUST be performed via the **`gh` CLI** as subprocesses.
- No Python GitHub API client (PyGithub, httpx + REST, GraphQL) is permitted.
- GitHub authentication is managed exclusively by `gh auth login` — perkins does not handle tokens directly.

## Output parsing

- All `gh` commands MUST use the `--json` flag to produce machine-readable output.
- JSON output MUST be parsed using the Python stdlib `json` module.
- Example commands:
  - Poll issues: `gh issue list --json number,title,body,labels,state`
  - Create PR: `gh pr create --title "..." --body "..." --base main`
  - Post comment: `gh issue comment {number} --body "..."`

## Error handling

- Non-zero exit from any `gh` command MUST be treated as an error: log stderr, report to Master, do not retry automatically.
- The Watcher's poll loop MUST catch `gh` failures and continue polling on the next interval rather than crashing the daemon.
