#!/bin/bash
# Full-stack code generation script
# Generates Python schemas, exports OpenAPI, and generates TypeScript client

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== Full-Stack Code Generation ==="
echo ""

# Step 1: Generate Python schemas from JSON Schema
echo "[1/4] Generating Python schemas..."
if [ -f "./scripts/generate.sh" ]; then
    ./scripts/generate.sh
else
    echo "  Skipping: generate.sh not found"
fi

# Step 2: Export OpenAPI from FastAPI
echo ""
echo "[2/4] Exporting OpenAPI spec..."
if uv run python scripts/export_openapi.py; then
    echo "  OpenAPI spec exported successfully"
else
    echo "  Warning: Could not export OpenAPI spec (is the API server configured?)"
    echo "  You may need to run 'uv run uvicorn src.main:app' first"
fi

# Step 3: Generate TypeScript + React Query from OpenAPI
echo ""
echo "[3/4] Generating TypeScript API client..."
if [ -f "./openapi.json" ]; then
    cd web
    if npm run generate:api; then
        echo "  TypeScript client generated successfully"
    else
        echo "  Warning: Could not generate TypeScript client"
    fi
    cd ..
else
    echo "  Skipping: openapi.json not found"
    echo "  Run step 2 first to export the OpenAPI spec"
fi

# Step 4: Verify types
echo ""
echo "[4/4] Type checking frontend..."
if [ -d "./web" ]; then
    cd web
    if npm run typecheck; then
        echo "  Type check passed"
    else
        echo "  Warning: Type check failed (this is expected if API is not generated yet)"
    fi
    cd ..
else
    echo "  Skipping: web directory not found"
fi

echo ""
echo "=== Generation complete ==="
