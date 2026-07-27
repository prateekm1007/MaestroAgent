# Controlled Transcript — Nora Fixture (P82 / FA33 regression)

> **Purpose:** This fixture is the canonical regression test for actor attribution
> correctness (P82) and the FA33 forbidden action (promoting non-user events to
> active user commitments). It must be ingested by the system on every PR, and
> the seven assertions in `tests/test_P82_controlled_transcript_nora.py` must
> all pass.
>
> **Origin:** External Audit #2 (2026-07-27) ran this transcript and found that
> the product misclassified the request (#3) and Nora's third-party promise (#5)
> as the user's active commitments, while silently dropping the cancellation (#6).
> That category failure is the reason this fixture exists.
>
> **Last-updated:** 2026-07-27

## Transcript

Meeting with Nora, 2026-07-27 10:00 UTC.

1. "I will send the audit report to Nora by Friday."          [USER COMMITMENT - EXPLICIT]
2. "Maybe I can review it sometime next week."                 [TENTATIVE - NOT A COMMITMENT]
3. "Can you send the report by Friday?"                        [REQUEST/QUESTION - NOT USER COMMITMENT]
4. "Just kidding, I will conquer Mars tomorrow."               [JOKE - NOT A COMMITMENT]
5. "Nora: I will send the pricing deck by Friday."             [THIRD-PARTY COMMITMENT - NORA'S, NOT USER'S]
6. "I will not send the audit report; the commitment is cancelled." [CANCELLATION]
7. "As Nora said, 'the Q3 numbers look strong.'"              [QUOTATION - NOT USER COMMITMENT]

## Expected Behavior (mechanically verifiable)

```python
EXPECTED = {
    "commitments_extracted": 1,   # Only #1
    "requests_detected": 1,       # #3
    "third_party_commitments": 1, # #5 (attributed to Nora, not user)
    "cancellations_detected": 1,  # #6 (resolves #1)
    "tentatives_detected": 1,     # #2
    "jokes_detected": 1,          # #4
    "quotations_detected": 1,     # #7
    "user_active_commitments": 0, # #1 cancelled by #6
    "nora_active_commitments": 1, # #5
}
```

## Critical Assertions

1. **User has ZERO active commitments** — the one user commitment (#1) was cancelled by #6.
2. **Nora has ONE active commitment** — sentence #5, attributed to her, not the user.
3. **Ask "What did I promise Nora?"** must return confidence < 0.1 OR contain "no evidence" / "cancelled" in the answer.
4. **Ask must NOT assert** the user promised to send the pricing deck — that was Nora's promise.
5. **Requests (#3) must not become commitments.** A question is not a promise.
6. **Jokes (#4) must not become commitments.** "Conquer Mars tomorrow" is not a commitment.
7. **Quotations (#7) must not become commitments.** "As Nora said, '...'" is reported speech.

## Why each sentence is in the fixture

- **#1 (user commitment):** the baseline positive. If this is missed, the classifier is under-extracting.
- **#2 (tentative):** tests the tentative hedge filter ("maybe", "sometime", "next week" with no firm date).
- **#3 (request):** the smoking gun from Audit #2. A question form ("Can you...?") must not be promoted to a user commitment. The actor is the user, but the event type is `request`, not `commitment`.
- **#4 (joke):** tests that absurd content ("conquer Mars tomorrow") is recognized as non-serious. The signal has commitment-shape ("I will") but the entity ("Mars") and tone flag it as a joke.
- **#5 (third-party promise):** the second smoking gun. "Nora: I will send..." attributes the commitment to Nora, not the user. The actor is `Nora`, not `user`. Without correct actor attribution, this becomes a user commitment to send the pricing deck.
- **#6 (cancellation):** the third smoking gun. "I will not send X; the commitment is cancelled" must transition commitment #1 from `active` to `cancelled`. Audit #2 found this was silently dropped.
- **#7 (quotation):** tests that reported speech ("As Nora said, '...'") is not promoted to a commitment. The user is reporting Nora's statement, not making one of their own.

## How to run the test

```bash
cd download/MaestroAgent/maestro-personal
PYTHONPATH=src python -m pytest tests/test_P82_controlled_transcript_nora.py -v
```

The test creates a fresh account, ingests this fixture via the real ingestion pipeline, and asserts the seven critical behaviors. Any failure is a release blocker.

## Governance citations

- **P1** (claim is not true until executed): the test must run on every PR, not just be present in the repo.
- **P11** (wiring): the test must ingest through the REAL ingestion path, not a mocked one.
- **P22** (regression test must execute the production path): unit tests on the classifier alone are insufficient; the test must post the transcript through `/api/signals` and assert at `/api/commitments`.
- **P35** (gate the journey, not the component): the test gates the full ingestion → classification → ledger → projection → Ask journey, not just the classifier's return value.
- **P82** (actor attribution correctness): the test enforces ≥95% attribution accuracy.
- **FA33** (promoting non-user events): any failure of this test is a FA33 violation and a release blocker.
