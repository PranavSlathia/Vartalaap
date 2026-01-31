#!/bin/bash
# =============================================================================
# Vartalaap Code Generation Script
# =============================================================================
# Generates Pydantic schemas from JSON Schema files and checks for DB changes.
#
# Usage:
#   ./scripts/generate.sh          # Run all generation steps
#   ./scripts/generate.sh schemas  # Only generate Pydantic schemas
#
# Prerequisites:
#   uv sync --extra dev
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           Vartalaap Code Generation                           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# =============================================================================
# Step 1: Generate Pydantic schemas from JSON Schema
# =============================================================================
generate_schemas() {
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│ [1/3] Generating Pydantic schemas from JSON Schema...          │"
    echo "└─────────────────────────────────────────────────────────────────┘"

    mkdir -p src/schemas

    for schema in schemas/*.json; do
        if [ -f "$schema" ]; then
            name=$(basename "$schema" .json)
            echo "  → Generating $name..."
            uv run datamodel-codegen \
                --input "$schema" \
                --output "src/schemas/${name}.py" \
                --output-model-type pydantic_v2.BaseModel \
                --use-annotated \
                --field-constraints \
                --use-default \
                --target-python-version 3.12 \
                --disable-timestamp \
                --use-standard-collections \
                --use-union-operator
        fi
    done

    # Add marker file
    cat > src/schemas/_generated.py << 'EOF'
# =============================================================================
# AUTO-GENERATED - DO NOT EDIT
# =============================================================================
# These schemas are generated from JSON Schema files in schemas/
# Regenerate with: ./scripts/generate.sh
#
# To modify a schema:
#   1. Edit the corresponding schemas/*.json file
#   2. Run ./scripts/generate.sh
#   3. Update src/db/models.py if needed
#   4. Run: make migration msg="description"
# =============================================================================
EOF

    echo "  ✓ Pydantic schemas generated"
    echo ""
}

# =============================================================================
# Step 2: Check for database schema changes
# =============================================================================
check_migrations() {
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│ [2/3] Checking for database schema changes...                  │"
    echo "└─────────────────────────────────────────────────────────────────┘"

    if [ -d "migrations/versions" ]; then
        # Check if there are pending changes without creating a migration
        CHANGES=$(uv run alembic check 2>&1) || true
        if echo "$CHANGES" | grep -q "FAILED"; then
            echo "  ⚠ Schema changes detected!"
            echo "  → Run: make migration msg=\"description\""
            echo "  → (Manual step to ensure meaningful commit messages)"
        else
            echo "  ✓ No schema changes detected"
        fi
    else
        echo "  → Alembic not initialized yet"
        echo "  → Run: uv run alembic init migrations"
    fi
    echo ""
}

# =============================================================================
# Step 3: Generate ER diagram (optional)
# =============================================================================
generate_er_diagram() {
    echo "┌─────────────────────────────────────────────────────────────────┐"
    echo "│ [3/3] Generating ER diagram...                                 │"
    echo "└─────────────────────────────────────────────────────────────────┘"

    # Check if models exist
    if [ ! -f "src/db/models.py" ]; then
        echo "  → Skipped (src/db/models.py not found)"
        echo ""
        return
    fi

    # Try to generate diagram
    uv run python -c "
from eralchemy2 import render_er
try:
    from src.db.models import SQLModel
    render_er(SQLModel.metadata, 'docs/er_diagram.png')
    print('  → Generated docs/er_diagram.png')
except Exception as e:
    print(f'  → Skipped ({e})')
" 2>/dev/null || echo "  → Skipped (eralchemy2 not installed or models not ready)"
    echo ""
}

# =============================================================================
# Main
# =============================================================================
case "${1:-all}" in
    schemas)
        generate_schemas
        ;;
    migrations)
        check_migrations
        ;;
    diagram)
        generate_er_diagram
        ;;
    all|*)
        generate_schemas
        check_migrations
        generate_er_diagram
        ;;
esac

echo "═══════════════════════════════════════════════════════════════════"
echo "Generation complete!"
echo "═══════════════════════════════════════════════════════════════════"
