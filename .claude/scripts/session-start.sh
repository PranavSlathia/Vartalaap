#!/usr/bin/env bash
# session-start.sh — Prints useful context at the start of each Claude session.
# Runs on SessionStart.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Vartalaap — Session Context"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Git branch
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
echo "  Branch:  $BRANCH"

# .env existence (never print contents)
if [[ -f "$PROJECT_ROOT/.env" ]]; then
  echo "  .env:    present"
else
  echo "  .env:    MISSING — copy .env.example and fill in API keys"
fi

# Uncommitted changes summary
CHANGED_COUNT=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
if [[ "$CHANGED_COUNT" -eq 0 ]]; then
  echo "  Changes: clean working tree"
else
  echo "  Changes: $CHANGED_COUNT file(s) modified/untracked"
  git status --short 2>/dev/null | head -10 | sed 's/^/           /'
  if [[ "$CHANGED_COUNT" -gt 10 ]]; then
    echo "           ... and $((CHANGED_COUNT - 10)) more"
  fi
fi

# Migration status
echo ""
echo "  Migration status:"
CURRENT=$(uv run alembic current 2>/dev/null | tail -1 || echo "  (could not check)")
HEAD=$(uv run alembic heads 2>/dev/null | tail -1 || echo "  (could not check)")
echo "    current: $CURRENT"
echo "    head:    $HEAD"

if [[ "$CURRENT" != "$HEAD" ]] && [[ -n "$CURRENT" ]] && [[ -n "$HEAD" ]]; then
  echo "  ⚠ Pending migrations! Run: uv run alembic upgrade head"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit 0
