# perkins

Perkins is an autonomous multi-agent development system that orchestrates AI developer agents to resolve GitHub issues end-to-end, from spec to merged PR.

## Prerequisites

- **Python >= 3.11**
- **[gh CLI](https://cli.github.com/)** — authenticated (`gh auth login`)
- **[cliplin](https://github.com/Rodrigonavarro23/cliplin)** — installed and available in PATH
- **Anthropic API key** — set as `ANTHROPIC_API_KEY` environment variable
- **cliplin-acd knowledge package** — install via:
  ```bash
  cliplin knowledge add https://github.com/Rodrigonavarro23/cliplin-knowledge
  ```

## Installation

```bash
pip install git+https://github.com/Rodrigonavarro23/perkins
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv add git+https://github.com/Rodrigonavarro23/perkins
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
