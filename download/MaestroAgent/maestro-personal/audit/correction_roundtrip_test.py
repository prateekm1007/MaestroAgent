#!/usr/bin/env python3
"""Correction round-trip test — Trust Gap #2.

Auditor's test: pick a signal the system cites for a question.
Correct/dismiss it. Re-ask the same question. If the corrected signal
is still cited → correction is write-only (gap confirmed). If it's
excluded → correction feeds back (gap closed).

This script traces the CODE PATH to determine whether corrected signals
are filtered in the Ask retrieval pipeline. It does NOT hit the live
API (that requires the full server + LLM); instead it inspects whether
the retrieval functions filter dismissed signals.

Findings are printed with a clear verdict.
"""
from __future__ import annotations
import sys
from pathlib import Path

# Make source importable
SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def check_fts_filtering():
    """Does semantic_search (BM25 path) filter dismissed signals?"""
    print("\n[1] BM25 / FTS retriever (semantic_retrieval.semantic_search)")
    print("    Query: SELECT signal_id, bm25(signals_fts) FROM signals_fts WHERE MATCH ?")
    print("    Then: SELECT * FROM signals WHERE signal_id IN (...)")

    # Check if propagate_correction removes from FTS
    import inspect
    from maestro_personal_shell import commitment_ledger, semantic_retrieval

    prop_src = inspect.getsource(commitment_ledger.propagate_correction)
    has_fts_removal = "delete_signal_from_fts" in prop_src

    print(f"    propagate_correction calls delete_signal_from_fts: {has_fts_removal}")
    if has_fts_removal:
        print("    → BM25 retriever: CORRECTED signals removed from FTS → NOT retrieved ✓")
        return True
    else:
        print("    → BM25 retriever: corrected signals STILL in FTS → GAP")
        return False


def check_specialist_filtering():
    """Do specialist retrievers filter dismissed signals?"""
    print("\n[2] Specialist retrievers (retrieval_ensemble._load_all_signals)")
    import inspect
    from maestro_personal_shell import retrieval_ensemble

    src = inspect.getsource(retrieval_ensemble._load_all_signals)
    print(f"    Source:")
    for line in src.strip().split("\n"):
        print(f"      {line}")

    filters_dismissed = ("dismissed" in src.lower() or "correction" in src.lower()
                         or 'metadata' in src.lower() and 'status' in src.lower())

    if filters_dismissed:
        print("    → Specialist retrievers: filter dismissed signals ✓")
        return True
    else:
        print("    → Specialist retrievers: NO filter on dismissed/corrected signals → GAP")
        print("      A corrected signal can still surface via entity/temporal/commitment/")
        print("      relationship/intent_keyword retrievers because they load ALL signals.")
        return False


def check_shell_filter_evidence():
    """Does shell.filter_evidence filter dismissed signals?"""
    print("\n[3] Shell.filter_evidence (final filter before LLM)")
    import inspect
    from maestro_personal_shell import shell

    src = inspect.getsource(shell.PersonalShell.filter_evidence)
    print(f"    Source:")
    for line in src.strip().split("\n"):
        print(f"      {line}")

    filters_dismissed = ("dismissed" in src.lower() or "correction" in src.lower())

    if filters_dismissed:
        print("    → filter_evidence: removes dismissed signals ✓")
        return True
    else:
        print("    → filter_evidence: does NOT filter dismissed/corrected signals → GAP")
        print("      (it filters model outputs and shadow signals, but not corrections)")
        return False


def check_commitments_filter():
    """Does the commitments router filter dismissed? (already confirmed in grep)"""
    print("\n[4] Commitments router (_filter_dismissed_commitments)")
    import inspect
    from maestro_personal_shell.routers import commitments

    has_filter = hasattr(commitments, "_filter_dismissed_commitments")
    if has_filter:
        src = inspect.getsource(commitments._filter_dismissed_commitments)
        filters_dismissed = "correction" in src.lower() or "dismissed" in src.lower()
        print(f"    _filter_dismissed_commitments exists: {has_filter}")
        print(f"    Filters on correction/dismissed: {filters_dismissed}")
        if filters_dismissed:
            print("    → Commitments router: filters dismissed ✓")
            return True
    print("    → Commitments router: GAP")
    return False


def main():
    print("=" * 72)
    print("TRUST GAP #2: Correction round-trip — is metadata['correction'] read downstream?")
    print("=" * 72)

    results = {
        "BM25/FTS retriever": check_fts_filtering(),
        "Specialist retrievers": check_specialist_filtering(),
        "Shell.filter_evidence": check_shell_filter_evidence(),
        "Commitments router": check_commitments_filter(),
    }

    print(f"\n{'='*72}")
    print("VERDICT")
    print(f"{'='*72}")
    for name, ok in results.items():
        print(f"  {name:25s} {'✓ filters dismissed' if ok else '✗ GAP — corrected signals can surface'}")

    all_ok = all(results.values())
    print()
    if all_ok:
        print("CORRECTION IS NOT WRITE-ONLY — all retrieval paths filter dismissed signals.")
        print("Trust gap #2 is CLOSED in code. (Live round-trip test still owed to confirm")
        print("end-to-end behavior, but the code paths are correct.)")
    else:
        gaps = [n for n, ok in results.items() if not ok]
        print(f"CORRECTION IS PARTIALLY WRITE-ONLY — {len(gaps)} retrieval path(s) have gaps:")
        for g in gaps:
            print(f"  - {g}")
        print()
        print("Fix: add a dismissed-signal filter to the gapped retrieval paths so")
        print("corrected signals are excluded from Ask evidence, not just from FTS.")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
