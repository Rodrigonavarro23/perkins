# perkins

Perkins is an autonomous multi-agent development system that orchestrates AI developer agents to resolve GitHub issues end-to-end, from spec to merged PR.

## Getting started

### 1. Install dependencies

**Python 3.11+** is required. Install with [uv](https://docs.astral.sh/uv/):

```bash
# perkins
uv tool install git+https://github.com/Rodrigonavarro23/perkins

# GitHub CLI — needed to read issues and open PRs
brew install gh        # macOS; see https://cli.github.com for other platforms
gh auth login

# cliplin — context and spec management
uv tool install git+https://github.com/Rodrigonavarro23/cliplin

# ACD knowledge package — framework docs and delivery contracts
cliplin knowledge add https://github.com/Rodrigonavarro23/cliplin-knowledge
```

### 2. Set your API key

Perkins supports **Anthropic** and **OpenAI** (and any model supported by LangChain's `init_chat_model`).

**Anthropic (default):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

**OpenAI:**
```bash
export OPENAI_API_KEY=sk-...
```

### 3. Initialize your project

Run this inside your repo:

```bash
cd /path/to/your-repo
perkins init
```

This generates `perkins.yaml`. Edit it and fill in your details:

```yaml
repo:
  name: your-project
  description: "Short description of what this repo does"
  github_repo: owner/repo        # auto-detected from git remote

orchestrator:
  provider: anthropic
  model: claude-opus-4-6         # or "openai:gpt-4o", "openai:gpt-4.1", etc.
  api_key_env: ANTHROPIC_API_KEY # or OPENAI_API_KEY

dev_agents:
  default_tool: claude-code      # or "gemini" or "cursor"
```

### 4. Start a session

Point perkins at a GitHub issue URL:

```bash
perkins start https://github.com/owner/repo/issues/123 --watch
```

`--watch` keeps the terminal open so you can answer questions from the agent as it works. Without it the session runs in the background and you connect later with `perkins chat`.

---

## Prerequisites

- **Python >= 3.11**
- **[gh CLI](https://cli.github.com/)** — authenticated (`gh auth login`)
- **[cliplin](https://github.com/Rodrigonavarro23/cliplin)** — installed and available in PATH
- **API key** — Anthropic (`ANTHROPIC_API_KEY`) or OpenAI (`OPENAI_API_KEY`)
- **cliplin-acd knowledge package** — install via:
  ```bash
  cliplin knowledge add https://github.com/Rodrigonavarro23/cliplin-knowledge
  ```

## Installation

```bash
uv tool install git+https://github.com/Rodrigonavarro23/perkins
```

## Usage

### Initialize a project

```bash
perkins init
```

Generates `perkins.yaml` in the current directory with configuration placeholders. Edit the file to set your project details. Re-running `init` preserves values you have already filled in.

### Start a session

```bash
perkins start <github-issue-url>
```

Launches an autonomous agent session to resolve the given GitHub issue. The session ID is printed on start.

### Start a session and wait for questions

```bash
perkins start <github-issue-url> --watch
```

Starts the session and then enters interactive chat mode. The agent can ask you questions during execution; you answer them directly in the terminal.

### Chat with a running session

```bash
perkins chat <session-id>
```

Connects to an already-running session to answer pending questions. Use `--watch` to poll continuously:

```bash
perkins chat <session-id> --watch
```

### Stop a session

```bash
perkins stop <session-id>
```

## Related projects

- [cliplin](https://github.com/Rodrigonavarro23/cliplin) — context and spec management tool used by perkins
- [cliplin-knowledge](https://github.com/Rodrigonavarro23/cliplin-knowledge) — ACD knowledge package with delivery contracts, TDRs, and framework docs
