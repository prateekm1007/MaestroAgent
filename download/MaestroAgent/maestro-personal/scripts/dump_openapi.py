"""
Dump the current OpenAPI schema from the FastAPI app to docs/openapi_schema.json.
Run this whenever the API surface changes.

Usage:
  python scripts/dump_openapi.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
os.environ.setdefault("MAESTRO_ENV", "dev")
os.environ.setdefault("ENV", "dev")

from maestro_personal_shell.api import app  # noqa: E402

schema = app.openapi()
out = REPO_ROOT / "docs" / "openapi_schema.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n")
print(f"Wrote {out} ({out.stat().st_size // 1024} KB)")
print(f"  Paths: {len(schema.get('paths', {}))}")
print(f"  Schemas: {len(schema.get('components', {}).get('schemas', {}))}")
print(f"  OpenAPI version: {schema.get('openapi')}")
