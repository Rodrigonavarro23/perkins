#!/usr/bin/env bash
# ACD Commit Validator — commit-msg stage.
# Validates UD-2: commit message format (ACD-session, Artifacts, Scenarios fields).
# Receives the path to the commit message file as $1.
# Exits 0 (PASS) or 1 (FAIL).
#
# AI CLI: claude (detected at install time). Override with ACD_AI_BIN env var.

ACD_AI_BIN="${ACD_AI_BIN:-claude}"
COMMIT_MSG_FILE="${1:-}"

if ! command -v "$ACD_AI_BIN" &>/dev/null; then
  echo "[ACD] ERROR: AI CLI '$ACD_AI_BIN' not found. Set ACD_AI_BIN to the correct binary." >&2
  exit 1
fi

# Adapter: invoke Claude Code with the prompt.
run_ai() {
  local prompt="$1"
  echo "$prompt" | "$ACD_AI_BIN" --print --allowedTools "Bash,Read,Glob,Grep"
}

if [ -z "$COMMIT_MSG_FILE" ] || [ ! -f "$COMMIT_MSG_FILE" ]; then
  echo "[ACD] ERROR: commit message file not found at '$COMMIT_MSG_FILE'." >&2
  exit 1
fi

COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Infrastructure-only skip: if message contains [skip-UD-2], pass.
if echo "$COMMIT_MSG" | grep -q "\[skip-UD-2\]"; then
  echo "[ACD] UD-2 skipped via [skip-UD-2] marker." >&2
  exit 0
fi

echo "[ACD] Validating commit message format (UD-2)..." >&2

PROMPT="Check this commit message for ACD UD-2 compliance. The message must contain: an 'ACD-session:' line, an 'Artifacts:' line, and a 'Scenarios:' line. If all three are present, output 'ACD-VALIDATION: PASS'. If any are missing, list which ones and output 'ACD-VALIDATION: FAIL'. Commit message: $(echo "$COMMIT_MSG" | head -20)"

OUTPUT=$(run_ai "$PROMPT" 2>&1) || true

echo "$OUTPUT"

if echo "$OUTPUT" | grep -q "ACD-VALIDATION: PASS"; then
  exit 0
else
  echo "" >&2
  echo "[ACD] UD-2 fix: add 'ACD-session:', 'Artifacts:', and 'Scenarios:' lines." >&2
  echo "[ACD]   Or add [skip-UD-2] with a justification for infra-only commits." >&2
  exit 1
fi
