---
tdr: "1.0"
id: "perkins-search"
title: "Perkins Web Search for ask_master Resolution"
summary: "httpx AsyncClient is the HTTP client for web search API calls in the Master's ask_master resolution tier. Web search is a middle tier between cliplin context and human escalation."
---

# rules

## Resolution tier

- Web search is an **optional middle tier** in the `ask_master` resolution chain, activated
  only when `search.enabled: true` in `perkins.yaml`.
- The resolution order MUST be:
  1. Cliplin context store (`context_query_documents`)
  2. LangGraph graph invocation (first pass)
  3. Web search + second graph invocation (only if `search.enabled=true`)
  4. Human escalation via `interrupt()`
- If `search.enabled` is `false` (default), steps 3 is skipped entirely and behavior is
  identical to the pre-search flow.

## HTTP client

- All web search API calls MUST use **`httpx.AsyncClient`** with a timeout of `5.0` seconds.
- No synchronous HTTP calls are permitted in the ask_master path; all calls MUST be awaited.
- On `httpx.TimeoutException` or any `httpx.HTTPStatusError`, the search MUST be treated as
  a non-result: log a warning and fall through to human escalation gracefully.
- The MCP server MUST NOT raise an exception or crash on search failure.

## Providers

- Supported providers in v1: `brave` and `serper`.
- Provider is configured via `search.provider` in `perkins.yaml` (default: `brave`).
- The API key is read from the environment variable named in `search.api_key_env`.
- If the env var is unset or empty at search time, log a warning
  (`"search.api_key_env is unset — skipping web search tier"`) and skip the search tier,
  falling through to human escalation. Do NOT raise an error.

## Brave Search API

- Endpoint: `https://api.search.brave.com/res/v1/web/search`
- Auth header: `X-Subscription-Token: <api_key>`
- Query params: `q=<question>`, `count=<max_results>`
- Result extraction: `response["web"]["results"]` → list of `{title, url, description}`

## Serper API

- Endpoint: `https://google.serper.dev/search`
- Auth header: `X-API-KEY: <api_key>`
- Request body (JSON): `{"q": "<question>", "num": <max_results>}`
- Result extraction: `response["organic"]` → list of `{title, link, snippet}`

## Result format

- Results MUST be normalized to a common structure before passing to the Master graph:
  `[{"title": str, "url": str, "snippet": str}]`
- Brave: `title` → `title`, `url` → `url`, `description` → `snippet`
- Serper: `title` → `title`, `link` → `url`, `snippet` → `snippet`
- Maximum results passed to the graph: `search.max_results` from config (default: 5).

## Second graph invocation

- After a successful web search, the Master graph MUST be invoked a second time with the
  search results appended to the context as a structured block:
  ```
  [WEB SEARCH RESULTS]
  1. <title> — <url>
     <snippet>
  ...
  ```
- If the graph produces a non-interrupt answer on the second invocation → return directly
  to the dev sub-agent. The human is NOT notified.
- If the graph raises `__interrupt__` again after the second invocation → escalate to human;
  the interrupt payload MUST include `"web_search_results": [{"title", "url", "snippet"}]`.
- If the search produced no results, skip the second invocation and escalate to human with
  `web_search_results: null`.

## Interrupt payload extension

- The interrupt payload structure is extended to include an optional field:
  `{"type": "ask_master", "issue_id": str, "question": str, "context": str, "web_search_results": list | null}`
- `web_search_results` is `null` when:
  - `search.enabled=false`
  - The search API call failed or timed out
  - The search returned no results
  - The api_key_env was unset
