# Quality Bars — Standards Every Fix Must Meet

## Code Quality

- **Trace before fix:** Capture the traceback / error / observed behavior before patching. Understand the root cause.
- **Fix the root cause:** Don't bandage symptoms. If the fix would only suppress the error without addressing why it happened, escalate.
- **No spray fixes:** When touching multiple return paths, verify the variable is defined on ALL paths. Test the abstention/error paths explicitly.
- **Test co-location:** Generated tests go next to the code they protect, not in a separate test graveyard.

## Verification Quality

- **Red/green proof:** Every fix must have a red/green proof — plant the bug, watch the test fail, fix it, watch it pass. A fix never shown to fail has not been shown to work.
- **Outcome verification:** After the fix, verify the FULL loop, not just the entry point. "Endpoint exists" ≠ "works end-to-end."
- **Fresh fetch for live claims:** Any claim about live state requires a fresh fetch at the moment of the claim. For client-rendered content, use a JS-executing instrument.

## Honesty Quality

- **No metric gaming:** Don't lower thresholds, narrow scopes, or seed synthetic data to make a metric read greener.
- **No over-claiming:** "Exists" ≠ "works." "Build-verified" ≠ "live." "Unit-tested" ≠ "execution-proven." State the correct tier.
- **Honest boundaries:** When hitting a limit, state it precisely. Diagnose as far as you can. Report the exact remaining step.

## Governance Quality

- **Independent critic:** The actor never grades its own homework. The GovernanceEnforcer's LLM critic is a separate context.
- **Human ratification for Level 3:** Governance edits, threshold changes, and architecture decisions require human approval. The swarm drafts; the human ratifies.
- **Case memory grows:** Every fixed bug generates a benchmark case, so the regression can't recur silently. The benchmark is the swarm's immune system.
