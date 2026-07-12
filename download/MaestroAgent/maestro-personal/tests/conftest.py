"""conftest.py — set up sys.path so maestro_personal_shell + maestro_cognitive_council + no_dilution_guard are importable."""

import os
import sys
import pathlib

# F8 fix: tests legitimately need to mint tokens for arbitrary emails
# (e.g. cross-user isolation tests need user A and user B). The production
# default is fail-closed; tests opt in via this env var.
os.environ.setdefault("MAESTRO_PERSONAL_ALLOW_ARBITRARY_EMAIL", "1")

# Add maestro-personal/src to path (the Personal shell package)
personal_src = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(personal_src) not in sys.path:
    sys.path.insert(0, str(personal_src))

# Add maestro-personal/tests to path (so no_dilution_guard is importable)
tests_dir = pathlib.Path(__file__).resolve().parent
if str(tests_dir) not in sys.path:
    sys.path.insert(0, str(tests_dir))

# Add backend/ to path so maestro_cognitive_council is importable
# (the Core lives in backend/maestro_cognitive_council/)
backend_dir = pathlib.Path(__file__).resolve().parents[2] / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))
