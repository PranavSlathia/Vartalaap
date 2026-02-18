#!/usr/bin/env bash
# subagent-quality-gate.sh — Quality reminders after subagent completes.
# Runs on SubagentStop. Checks what changed and prints domain-specific reminders.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

# Get list of changed files (staged + unstaged, relative to last commit)
CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null || true)
STAGED_FILES=$(git diff --name-only --cached 2>/dev/null || true)
ALL_CHANGED="$CHANGED_FILES"$'\n'"$STAGED_FILES"

if [[ -z "$(echo "$ALL_CHANGED" | tr -d '[:space:]')" ]]; then
  exit 0  # No changes, nothing to check
fi

REMINDERS=()

# Voice pipeline changes → latency smoke test
if echo "$ALL_CHANGED" | grep -qE "^src/core/pipeline\.py$|^src/services/"; then
  REMINDERS+=("VOICE PIPELINE changed → Run latency smoke test: uv run python scripts/voice_test.py")
fi

# Database model changes → generate migration
if echo "$ALL_CHANGED" | grep -q "^src/db/models\.py$"; then
  REMINDERS+=("DB MODEL changed → Generate migration: make migration msg='<description>' && uv run alembic upgrade head")
fi

# Migration files changed → apply and re-export
if echo "$ALL_CHANGED" | grep -qE "^migrations/versions/"; then
  REMINDERS+=("MIGRATION changed → Apply: uv run alembic upgrade head && python scripts/export_openapi.py")
fi

# Web source changed (non-generated) → typecheck
WEB_NON_GEN=$(echo "$ALL_CHANGED" | grep "^web/src/" | grep -vE "^web/src/api/(endpoints|model)/" || true)
if [[ -n "$WEB_NON_GEN" ]]; then
  REMINDERS+=("WEB FRONTEND changed → Run: cd web && npm run typecheck")
fi

# Business config or prompts changed → reload/test
if echo "$ALL_CHANGED" | grep -qE "^config/.*\.yaml$|^src/prompts/"; then
  REMINDERS+=("CONFIG/PROMPTS changed → Reload business config and test in admin voice test page")
fi

# JSON schemas changed → regenerate Pydantic
if echo "$ALL_CHANGED" | grep -qE "^schemas/.*\.json$"; then
  REMINDERS+=("JSON SCHEMA changed → Regenerate Pydantic: ./scripts/generate.sh")
fi

# Warn if generated files were modified (shouldn't happen with pre-edit-guard, but double-check)
if echo "$ALL_CHANGED" | grep -qE "^src/schemas/[^/]+\.py$"; then
  REMINDERS+=("WARNING: src/schemas/*.py (generated) was modified — revert and use ./scripts/generate.sh instead")
fi

# Print all reminders
if [[ ${#REMINDERS[@]} -gt 0 ]]; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Quality Gate Reminders"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  for reminder in "${REMINDERS[@]}"; do
    echo "  ▸ $reminder"
  done
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
fi

exit 0
