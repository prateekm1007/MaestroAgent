# Voided Benchmark Artifacts

Files in this directory are VOID per the anti-gaming clauses in
`SCORING_SYSTEM.md`. They must not be cited as evidence for any score.

## ablation_round68.json

**VOID reason:** Metadata-consistency violation (anti-gaming clause 2).
- Top-level `llm_active: True` contradicts per-row data (all 30 rows
  show `llm_active: False`).
- The summary claims the LLM was active; the row-level data proves it
  was not. The file shipped a lie as its headline.

**Honest replacement:** `ablation_matrix_results.json` in the parent
directory contains the real ablation with a genuine BM25 comparison arm.
That file is the one to trust for AI Quality scoring.

**Do not delete this file.** It is retained as evidence of the VOID
condition and to prevent re-introduction. The `verify_benchmark.sh`
script in `audit_scripts/` will reject any commit that moves it back
to the parent directory.
