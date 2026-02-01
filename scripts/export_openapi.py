#!/usr/bin/env python3
"""Export OpenAPI spec from FastAPI application.

This script exports the OpenAPI JSON specification from the FastAPI app
for use with frontend code generators like Orval.

Usage:
    uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app


def main() -> None:
    """Export OpenAPI spec to openapi.json."""
    output_path = Path(__file__).parent.parent / "openapi.json"

    openapi_spec = app.openapi()

    with open(output_path, "w") as f:
        json.dump(openapi_spec, f, indent=2)

    print(f"OpenAPI spec exported to {output_path}")
    print(f"  - Paths: {len(openapi_spec.get('paths', {}))}")
    print(f"  - Schemas: {len(openapi_spec.get('components', {}).get('schemas', {}))}")


if __name__ == "__main__":
    main()
