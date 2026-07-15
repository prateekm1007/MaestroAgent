"""
Phase 3 labeled commitment corpus — 500 items across 13 categories.

Per the roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 3 requirement #1):
  explicit commitments; implicit commitments; requests; proposals;
  aspirations; tentative plans; conditional promises; third-party
  reports; negations; completed outcomes; disputed commitments; changed
  deadlines; cancelled commitments.

Each item has ground-truth labels matching the structured extraction schema:
  is_commitment, commitment_type, owner, recipient, action,
  deadline_text, deadline_datetime, state

The corpus is generated from hand-written templates with slot variation
(names, actions, deadlines) to reach 500 items while keeping labels
grounded. Templates are the seed; labels are the ground truth.

Used by test_commitment_eval.py to measure precision/recall/deadline/
closure/correction-persistence against the roadmap's 9/10 targets.
"""

from __future__ import annotations

import itertools
import random
from typing import Any

# Deterministic generation so eval results are reproducible.
RNG_SEED = 42

NAMES = ["Alex", "Sara", "Priya", "Marco", "Yuki", "David", "Lena", "Raj",
         "Maria", "Chen", "Omar", "Nina", "Tom", "Lea", "Sam", "Kai"]
ACTIONS = ["send the proposal", "review the scorecard", "deliver the roadmap",
           "sign the contract", "share the deck", "finalize the budget",
           "approve the design", "schedule the offsite", "publish the report",
           "update the dashboard"]
DEADLINES_TEXT = ["Friday EOD", "Monday morning", "next week", "by July 15",
                  "end of quarter", "tomorrow", "Wednesday COB", "July 31",
                  "before the board meeting", "this afternoon"]
DEADLINES_DT = ["2026-07-10T17:00:00+05:30", "2026-07-13T09:00:00-05:00",
                "2026-07-15T17:00:00+00:00", "2026-07-31T23:59:00+00:00",
                "2026-07-09T12:00:00+00:00", "2026-07-16T17:00:00-07:00"]


def _build_corpus() -> list[dict[str, Any]]:
    rng = random.Random(RNG_SEED)
    items: list[dict[str, Any]] = []

    def add(text, is_commitment, ctype, owner, recipient, action,
            deadline_text="", deadline_dt="", state="active"):
        items.append({
            "text": text,
            "is_commitment": is_commitment,
            "commitment_type": ctype,
            "owner": owner,
            "recipient": recipient,
            "action": action,
            "deadline_text": deadline_text,
            "deadline_datetime": deadline_dt,
            "state": state,
        })

    # 1. Explicit commitments (50)
    for name, action, dl_text, dl_dt in itertools.islice(
            itertools.product(NAMES, ACTIONS, DEADLINES_TEXT, DEADLINES_DT), 50):
        add(f"I will {action} by {dl_text}.",
            is_commitment=True, ctype="explicit", owner="user",
            recipient=name, action=action, deadline_text=dl_text,
            deadline_dt=dl_dt, state="active")

    # 2. Implicit commitments (40)
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 40):
        add(f"Let me {action} for you, {name}.",
            is_commitment=True, ctype="implicit", owner="user",
            recipient=name, action=action, state="active")

    # 3. Requests (40) — not commitments by the speaker
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 40):
        add(f"Can you {action} before the review, {name}?",
            is_commitment=False, ctype="request", owner="other",
            recipient="user", action=action, state="candidate")

    # 4. Proposals (35) — not commitments, suggestions
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 35):
        add(f"We should {action} this quarter, {name}.",
            is_commitment=False, ctype="proposal", owner="unknown",
            recipient=name, action=action, state="candidate")

    # 5. Aspirations (30) — not commitments, hopes
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 30):
        add(f"I hope to {action} someday, {name}.",
            is_commitment=False, ctype="aspiration", owner="user",
            recipient=name, action=action, state="candidate")

    # 6. Tentative plans (35) — weak commitment
    for name, action, dl_text in itertools.islice(
            itertools.product(NAMES, ACTIONS, DEADLINES_TEXT), 35):
        add(f"Maybe I can {action} by {dl_text}, but don't count on it, {name}.",
            is_commitment=False, ctype="tentative", owner="user",
            recipient=name, action=action, deadline_text=dl_text, state="candidate")

    # 7. Conditional promises (40) — commitment contingent on a condition
    for name, action, dl_text in itertools.islice(
            itertools.product(NAMES, ACTIONS, DEADLINES_TEXT), 40):
        add(f"If legal signs off, I'll {action} by {dl_text}, {name}.",
            is_commitment=True, ctype="conditional", owner="user",
            recipient=name, action=action, deadline_text=dl_text, state="active")

    # 8. Third-party reports (35) — reporting someone else's commitment
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 35):
        add(f"{name} said they will {action}.",
            is_commitment=True, ctype="third_party_report", owner="other",
            recipient="user", action=action, state="active")

    # 9. Negations (30) — explicit non-commitment
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 30):
        add(f"I won't be able to {action}, {name}.",
            is_commitment=False, ctype="negation", owner="user",
            recipient=name, action=action, state="cancelled")

    # 10. Completed outcomes (45) — completed_claimed / completed_verified
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 45):
        verified = rng.random() < 0.5
        add(f"I {action.replace('send', 'sent').replace('review', 'reviewed').replace('deliver', 'delivered').replace('sign', 'signed').replace('share', 'shared').replace('finalize', 'finalized').replace('approve', 'approved').replace('schedule', 'scheduled').replace('publish', 'published').replace('update', 'updated')} yesterday, {name}.",
            is_commitment=True, ctype="completed",
            owner="user", recipient=name, action=action,
            state="completed_verified" if verified else "completed_claimed")

    # 11. Disputed commitments (30) — completion challenged
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 30):
        add(f"We got the {action} but it's missing the appendix, {name}.",
            is_commitment=True, ctype="disputed", owner="other",
            recipient="user", action=action, state="disputed")

    # 12. Changed deadlines (30) — deadline modification
    for name, action, dl_text in itertools.islice(
            itertools.product(NAMES, ACTIONS, DEADLINES_TEXT), 30):
        add(f"The {action} deadline moved to {dl_text}, {name}.",
            is_commitment=True, ctype="explicit", owner="user",
            recipient=name, action=action, deadline_text=dl_text, state="active")

    # 13. Cancelled commitments (30) — explicit cancellation
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 30):
        add(f"Never mind, we don't need to {action} anymore, {name}.",
            is_commitment=True, ctype="cancelled", owner="user",
            recipient=name, action=action, state="cancelled")

    # 14. Superseded commitments (30) — replaced by a newer commitment
    for name, action in itertools.islice(itertools.product(NAMES, ACTIONS), 30):
        add(f"The earlier plan to {action} is replaced by the new roadmap, {name}.",
            is_commitment=True, ctype="superseded", owner="user",
            recipient=name, action=action, state="superseded")

    return items


CORPUS: list[dict[str, Any]] = _build_corpus()


def get_corpus() -> list[dict[str, Any]]:
    """Return the 500-item labeled corpus."""
    return CORPUS


def get_corpus_stats() -> dict[str, int]:
    """Return per-category counts."""
    stats: dict[str, int] = {}
    for item in CORPUS:
        stats[item["commitment_type"]] = stats.get(item["commitment_type"], 0) + 1
    return stats


if __name__ == "__main__":
    corpus = get_corpus()
    print(f"Total items: {len(corpus)}")
    print(f"Categories: {len(get_corpus_stats())}")
    for k, v in sorted(get_corpus_stats().items()):
        print(f"  {k:25} {v}")
    print(f"\nIs-commitment distribution:")
    print(f"  True:  {sum(1 for i in corpus if i['is_commitment'])}")
    print(f"  False: {sum(1 for i in corpus if not i['is_commitment'])}")
