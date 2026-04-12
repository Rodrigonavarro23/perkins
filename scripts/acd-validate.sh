#!/usr/bin/env bash
# ACD Commit Validator — pre-commit stage.
# Validates staged artifacts, test coverage, and traceability (AC-*, UD-1, TR-*).
# UD-2 (commit message format) is handled by the separate commit-msg hook.
# Exits 0 (PASS) or 1 (FAIL).
#
# AI CLI: claude (detected at install time). Override with ACD_AI_BIN env var.

ACD_AI_BIN="${ACD_AI_BIN:-claude}"

if ! command -v "$ACD_AI_BIN" &>/dev/null; then
  echo "[ACD] ERROR: AI CLI '$ACD_AI_BIN' not found. Set ACD_AI_BIN to the correct binary." >&2
  exit 1
fi

# Adapter: invoke Claude Code with the prompt.
run_ai() {
  local prompt="$1"
  echo "$prompt" | "$ACD_AI_BIN" --print --allowedTools "Bash,Read,Glob,Grep"
}

# If nothing is staged, skip validation.
STAGED=$(git diff --cached --name-only 2>/dev/null)
if [ -z "$STAGED" ]; then
  echo "[ACD] No staged files — skipping validation." >&2
  exit 0
fi

echo "[ACD] Running acd-commit-validator (pre-commit stage) on staged files:" >&2
echo "$STAGED" | sed 's/^/  /' >&2

PROMPT="Run the acd-commit-validator skill on the current staged changes. Use 'git diff --cached --name-only' and 'git diff --cached --stat' to see what is staged. Do NOT check UD-2 (commit message format) — that is handled by a separate commit-msg hook. Focus on: AC-1 (feature coverage), AC-2 (@constraints block), AC-3 (governed_by paths exist), AC-4 (scenario status), UD-1 (tests present), UD-3 (branch warning), TR-1 (orphan code), TR-2 (WIP marker). For infra-only commits (no .go/.ts/.py production files staged), pass AC-1, UD-1 and TR-1 automatically. Produce the full structured report and end with exactly ACD-VALIDATION: PASS or ACD-VALIDATION: FAIL."

OUTPUT=$(run_ai "$PROMPT" 2>&1) || true

echo "$OUTPUT"

if echo "$OUTPUT" | grep -q "ACD-VALIDATION: PASS"; then
  exit 0
else
  echo "" >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  echo "Commit blocked by ACD pre-commit validator." >&2
  echo "Fix the violations above and retry." >&2
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" >&2
  exit 1
fi
