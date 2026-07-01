"""
V8 Personal Mode — Phase 1 Infrastructure.

A separate codebase namespace for personal cognitive aid. Fully
separated from the OEM namespace (Guideline P2). The trust layers are
different. The data models are different. The consent primitives
are different.

Modules:
- consent.py — ConsentStore (per-source consent primitive, Guideline P3)
- mode.py — ModeManager (Work/Personal/Both separation, Guideline P10)
- incognito.py — IncognitoSession (no data persisted, Guideline P6)
- expiry.py — DataExpiry (24-month default, Guideline P7)
- dashboard.py — WhatMaestroKnows (transparency dashboard, Guideline P8)
- local.py — LocalFirstConfig (LOCAL_ONLY mode, Guideline P5)
- store.py — PersonalDataStore (the personal data store, separate from OEM)
"""

from __future__ import annotations

# Version
__version__ = "0.1.0"

# Guideline P2: This namespace MUST NOT import from the OEM namespace.
# The two namespaces communicate only through documented, audited
# boundary layers. This is enforced by the test:
#   grep for OEM imports in personal/ → zero matches
