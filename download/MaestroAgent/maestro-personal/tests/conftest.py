"""conftest.py — set up sys.path so maestro_personal + maestro_cognitive_council are importable."""

import sys
import pathlib

# Add maestro-personal/src to path
personal_src = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(personal_src) not in sys.path:
    sys.path.insert(0, str(personal_src))

# Add backend/ to path so maestro_cognitive_council is importable
# (the Core lives in backend/maestro_cognitive_council/)
backend_dir = pathlib.Path(__file__).resolve().parents[2] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
