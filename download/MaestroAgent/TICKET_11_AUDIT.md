# TICKET-11: ask.py Audit for Shadowed Imports + Silent Excepts

**Date:** 2026-07-25
**Auditor:** CTO (GLM)
**Method:** grep for every local import + every bare except Exception in ask.py

## Findings

### P66 (shadowed imports) — NO VIOLATIONS FOUND ✓

The module-level import at line 19-21:
```python
from maestro_personal_shell.reconcile import (
    reconcile_signals_for_user,
    filter_for_promise_query,
    ...
)
```

No local import of `reconcile_signals_for_user` or `filter_for_promise_query` exists
inside any function. The P66 fix (commit from earlier today) is holding — line 1981
even has a comment: "P66 (seventh audit): DO NOT re-import reconcile_signals_for_user here".

### P67 (silent debug-level excepts on primary paths) — NO VIOLATIONS FOUND ✓

The outer RC2 fast-path except at line 872 uses `logger.warning` (not `logger.debug`):
```python
logger.warning("P67: RC2 ledger-read fast path failed (falling through to general path): %s", e)
```

10 `logger.debug` except blocks remain, but all are on genuine fallback/optional paths:
- metadata parsing (2 instances)
- entity resolution fallback (2 instances)
- temporal filter fallback (1 instance)
- broad query handler fallback (1 instance)
- topic-word search fallback (1 instance)
- ledger query fallback (1 instance)
- change/attention query fallback (2 instances)

All are labeled "(non-fatal)" or "(non-blocking)" — they're legitimate fallbacks, not
primary-path silence.

## Verdict

TICKET-11 is COMPLETE. No P66 or P67 violations found in ask.py. The earlier fixes
(from the seventh audit) are holding.
