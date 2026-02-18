#!/usr/bin/env bash
# post-edit-lint.sh — Auto-lints after Edit or Write tool calls.
# Runs on PostToolUse for Edit and Write tool calls.

set -euo pipefail

# Extract file_path from the tool input JSON
FILE_PATH="${CLAUDE_TOOL_INPUT_file_path:-}"

if [[ -z "$FILE_PATH" ]]; then
  if [[ -n "${CLAUDE_TOOL_INPUT:-}" ]]; then
    FILE_PATH=$(echo "$CLAUDE_TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('file_path',''))" 2>/dev/null || true)
  fi
fi

if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

FILE_PATH="${FILE_PATH#./}"

# Skip generated files — they don't need linting
if [[ "$FILE_PATH" =~ ^src/schemas/[^/]+\.py$ ]] || \
   [[ "$FILE_PATH" =~ ^web/src/api/endpoints/ ]] || \
   [[ "$FILE_PATH" =~ ^web/src/api/model/ ]]; then
  exit 0
fi

# Determine project root (script lives in .claude/scripts/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Python files — run ruff with auto-fix
if [[ "$FILE_PATH" =~ \.py$ ]]; then
  ABS_PATH="$PROJECT_ROOT/$FILE_PATH"
  if [[ -f "$ABS_PATH" ]]; then
    echo "[post-edit-lint] Linting $FILE_PATH with ruff..."
    cd "$PROJECT_ROOT"
    if ! uv run ruff check "$ABS_PATH" --fix-only --quiet 2>&1; then
      echo "[post-edit-lint] ruff found issues in $FILE_PATH — check above for details"
    fi
    # Check for remaining issues (no fix available)
    REMAINING=$(uv run ruff check "$ABS_PATH" --output-format=concise 2>&1 || true)
    if [[ -n "$REMAINING" ]]; then
      echo "[post-edit-lint] Remaining lint issues:"
      echo "$REMAINING"
    fi
  fi
fi

# TypeScript / TSX files — run tsc type check
if [[ "$FILE_PATH" =~ \.(ts|tsx)$ ]]; then
  WEB_DIR="$PROJECT_ROOT/web"
  if [[ -d "$WEB_DIR" ]]; then
    echo "[post-edit-lint] Type-checking TypeScript (cd web && npx tsc --noEmit)..."
    cd "$WEB_DIR"
    TSC_OUTPUT=$(npx tsc --noEmit 2>&1 || true)
    if [[ -n "$TSC_OUTPUT" ]]; then
      echo "[post-edit-lint] TypeScript errors found:"
      echo "$TSC_OUTPUT"
    else
      echo "[post-edit-lint] TypeScript: no type errors"
    fi
  fi
fi

exit 0
