"""
Phase 8 Copilot benchmark — 30 simulated live conversations.

The roadmap (ROAD_TO_9_OF_10_AFTER_395558A.md Phase 8) requires 30
conversations covering 14 features:
  - interruptions
  - filler
  - corrections
  - sarcasm
  - tentative statements
  - changed positions
  - incomplete sentences
  - multiple speakers
  - ambiguous pronouns
  - explicit commitments
  - revoked commitments
  - negotiation anchors
  - concessions
  - disagreement

Each conversation has:
  - conversation_id: unique identifier
  - entity: the person being met with
  - features: which of the 14 features this conversation exercises
  - transcript: list of {speaker, text} chunks
  - 30_day_history: signals to seed as prior context
  - expected_commitments: commitments that should be extracted
  - expected_revocations: commitments that should be detected as revoked
  - expected_suggestions: topics the copilot should surface
  - forbidden_suggestions: topics that should NOT appear (hallucination check)

The benchmark runs each conversation twice:
  1. No history (cold start)
  2. With 30-day history (warm start)

The lift (history - no-history) measures whether history makes the
copilot genuinely better.
"""

from __future__ import annotations

from typing import Any


def _build_conversations() -> list[dict[str, Any]]:
    convs: list[dict[str, Any]] = []

    def add(cid, entity, features, transcript, history, exp_comm, exp_revoc, exp_sugg, forb_sugg):
        convs.append({
            "conversation_id": cid,
            "entity": entity,
            "features": features,
            "transcript": transcript,
            "history_signals": history,
            "expected_commitments": exp_comm,
            "expected_revocations": exp_revoc,
            "expected_suggestions": exp_sugg,
            "forbidden_suggestions": forb_sugg,
        })

    # 1. Explicit commitment + interruption
    add("conv-001", "Alex",
        ["explicit_commitments", "interruptions"],
        [
            {"speaker": "Alex", "text": "So about the proposal, I'll—"},
            {"speaker": "You", "text": "Sorry to interrupt, when can you send it?"},
            {"speaker": "Alex", "text": "No problem. I will send the proposal by Friday EOD."},
        ],
        [{"entity": "Alex", "text": "I will send the proposal", "signal_type": "commitment_made", "timestamp": "2026-06-15T10:00:00Z"}],
        [{"entity": "Alex", "text": "send the proposal by Friday EOD", "type": "explicit"}],
        [],
        ["proposal", "Friday"],
        ["budget", "lawsuit"])

    # 2. Revoked commitment + correction
    add("conv-002", "Maria",
        ["revoked_commitments", "corrections"],
        [
            {"speaker": "Maria", "text": "Actually, I said I'd send the report but I can't anymore."},
            {"speaker": "You", "text": "Wait, you committed to it last week."},
            {"speaker": "Maria", "text": "I know, I know. I'm correcting myself — the report is cancelled. Something came up."},
        ],
        [{"entity": "Maria", "text": "I will send the report", "signal_type": "commitment_made", "timestamp": "2026-06-20T10:00:00Z"}],
        [],
        [{"entity": "Maria", "text": "report is cancelled", "type": "revoked"}],
        ["cancelled", "report"],
        ["proposal", "contract"])

    # 3. Sarcasm + tentative
    add("conv-003", "Sam",
        ["sarcasm", "tentative_statements"],
        [
            {"speaker": "Sam", "text": "Oh sure, I'll definitely have the budget ready. Just like I definitely had it last time."},
            {"speaker": "You", "text": "Is that a maybe?"},
            {"speaker": "Sam", "text": "Maybe I can try to get it done, but don't count on it."},
        ],
        [{"entity": "Sam", "text": "I will prepare the budget", "signal_type": "commitment_made", "timestamp": "2026-06-18T10:00:00Z"}],
        [],
        [],
        ["budget"],
        ["contract", "lawsuit"])

    # 4. Changed position + negotiation anchor
    add("conv-004", "Priya",
        ["changed_positions", "negotiation_anchors"],
        [
            {"speaker": "Priya", "text": "I was thinking $50k, but actually let me reconsider — $75k is more realistic."},
            {"speaker": "You", "text": "That's a big jump."},
            {"speaker": "Priya", "text": "I know. My anchor is $75k. Let's work from there."},
        ],
        [{"entity": "Priya", "text": "I will send the pricing", "signal_type": "commitment_made", "timestamp": "2026-06-22T10:00:00Z"}],
        [],
        [],
        ["75k", "pricing", "anchor"],
        ["budget", "report"])

    # 5. Multiple speakers + ambiguous pronouns
    add("conv-005", "Team",
        ["multiple_speakers", "ambiguous_pronouns"],
        [
            {"speaker": "Alex", "text": "He said he'd handle it."},
            {"speaker": "Maria", "text": "Wait, who's 'he'?"},
            {"speaker": "Alex", "text": "David. He'll send the contract."},
            {"speaker": "David", "text": "I will? I mean, yes, I will send the contract by Tuesday."},
        ],
        [{"entity": "David", "text": "I will send the contract", "signal_type": "commitment_made", "timestamp": "2026-06-25T10:00:00Z"}],
        [{"entity": "David", "text": "send the contract by Tuesday", "type": "explicit"}],
        [],
        ["contract", "David", "Tuesday"],
        ["budget", "lawsuit"])

    # 6. Filler + incomplete sentences
    add("conv-006", "Morgan",
        ["filler", "incomplete_sentences"],
        [
            {"speaker": "Morgan", "text": "So, um, I was thinking about, you know, the roadmap and..."},
            {"speaker": "You", "text": "Go on."},
            {"speaker": "Morgan", "text": "I'll, uh, I'll have it ready by... well, let me get back to you on the date."},
        ],
        [{"entity": "Morgan", "text": "I will deliver the roadmap", "signal_type": "commitment_made", "timestamp": "2026-06-19T10:00:00Z"}],
        [],
        [],
        ["roadmap"],
        ["contract", "lawsuit"])

    # 7. Concession + disagreement
    add("conv-007", "Avery",
        ["concessions", "disagreement"],
        [
            {"speaker": "Avery", "text": "I think we need two more weeks for the migration."},
            {"speaker": "You", "text": "Two weeks? We agreed on one."},
            {"speaker": "Avery", "text": "I disagree — one week isn't enough. But fine, I'll concede. One week, but I need more resources."},
        ],
        [{"entity": "Avery", "text": "I will complete the migration", "signal_type": "commitment_made", "timestamp": "2026-06-21T10:00:00Z"}],
        [{"entity": "Avery", "text": "one week for the migration", "type": "concession"}],
        [],
        ["migration", "one week", "resources"],
        ["budget", "report"])

    # 8. Explicit commitment (clean)
    add("conv-008", "Marco",
        ["explicit_commitments"],
        [
            {"speaker": "Marco", "text": "I will send the security audit by next Wednesday."},
            {"speaker": "You", "text": "Great, thank you."},
        ],
        [{"entity": "Marco", "text": "I will send the security audit", "signal_type": "commitment_made", "timestamp": "2026-06-23T10:00:00Z"}],
        [{"entity": "Marco", "text": "send the security audit by next Wednesday", "type": "explicit"}],
        [],
        ["security audit", "Wednesday"],
        ["budget", "lawsuit"])

    # 9. Revoked + new commitment
    add("conv-009", "Yuki",
        ["revoked_commitments", "explicit_commitments"],
        [
            {"speaker": "Yuki", "text": "I can't do the old plan anymore. That's off."},
            {"speaker": "You", "text": "OK, what about the new roadmap?"},
            {"speaker": "Yuki", "text": "The new roadmap I can commit to. I'll deliver it by Friday."},
        ],
        [{"entity": "Yuki", "text": "I will deliver the old plan", "signal_type": "commitment_made", "timestamp": "2026-06-16T10:00:00Z"}],
        [{"entity": "Yuki", "text": "deliver the new roadmap by Friday", "type": "explicit"}],
        [{"entity": "Yuki", "text": "old plan is off", "type": "revoked"}],
        ["roadmap", "Friday", "new"],
        ["budget", "lawsuit"])

    # 10. Correction + filler
    add("conv-010", "David",
        ["corrections", "filler"],
        [
            {"speaker": "David", "text": "I said Monday, but, um, actually I meant Tuesday."},
            {"speaker": "You", "text": "Tuesday works."},
            {"speaker": "David", "text": "Yeah, sorry about that. Tuesday for sure."},
        ],
        [{"entity": "David", "text": "I will send the contract", "signal_type": "commitment_made", "timestamp": "2026-06-24T10:00:00Z"}],
        [],
        [],
        ["Tuesday"],
        ["budget", "lawsuit"])

    # 11-20: More combinations covering remaining features
    add("conv-011", "Lena",
        ["interruptions", "explicit_commitments"],
        [{"speaker": "Lena", "text": "I'll get the de—"}, {"speaker": "You", "text": "When?"}, {"speaker": "Lena", "text": "I will send the deck by tomorrow."}],
        [{"entity": "Lena", "text": "I will send the deck", "signal_type": "commitment_made", "timestamp": "2026-06-17T10:00:00Z"}],
        [{"entity": "Lena", "text": "send the deck by tomorrow", "type": "explicit"}], [],
        ["deck", "tomorrow"], ["budget"])

    add("conv-012", "Raj",
        ["sarcasm", "disagreement"],
        [{"speaker": "Raj", "text": "Sure, because the last plan worked SO well."}, {"speaker": "You", "text": "You disagree?"}, {"speaker": "Raj", "text": "I disagree with the timeline. It's unrealistic."}],
        [{"entity": "Raj", "text": "I will review the timeline", "signal_type": "commitment_made", "timestamp": "2026-06-26T10:00:00Z"}],
        [], [], ["timeline", "disagree"], ["budget", "contract"])

    add("conv-013", "Alex",
        ["negotiation_anchors", "concessions"],
        [{"speaker": "Alex", "text": "My starting point is $100k."}, {"speaker": "You", "text": "That's high."}, {"speaker": "Alex", "text": "OK, I'll move to $90k as a concession."}],
        [{"entity": "Alex", "text": "I will send the pricing", "signal_type": "commitment_made", "timestamp": "2026-06-27T10:00:00Z"}],
        [], [], ["100k", "90k", "concession"], ["budget", "report"])

    add("conv-014", "Maria",
        ["tentative_statements", "filler"],
        [{"speaker": "Maria", "text": "Maybe, um, I could try to, you know, get it done by next week? But I'm not sure."}],
        [{"entity": "Maria", "text": "I will send the report", "signal_type": "commitment_made", "timestamp": "2026-06-28T10:00:00Z"}],
        [], [], ["report", "tentative"], ["budget", "contract"])

    add("conv-015", "Sam",
        ["changed_positions", "corrections"],
        [{"speaker": "Sam", "text": "I said Friday, but I'm changing that to Monday."}, {"speaker": "You", "text": "Why the change?"}, {"speaker": "Sam", "text": "Correction — I need the weekend. Monday is better."}],
        [{"entity": "Sam", "text": "I will send the budget", "signal_type": "commitment_made", "timestamp": "2026-06-29T10:00:00Z"}],
        [], [], ["Monday", "correction"], ["budget", "lawsuit"])

    add("conv-016", "Priya",
        ["multiple_speakers", "filler"],
        [{"speaker": "Priya", "text": "So, um, Alex and I were thinking..."}, {"speaker": "Alex", "text": "We'll, uh, split the work."}, {"speaker": "Priya", "text": "Yeah, I'll take the design, Alex takes the code."}],
        [{"entity": "Priya", "text": "I will do the design", "signal_type": "commitment_made", "timestamp": "2026-06-30T10:00:00Z"}],
        [{"entity": "Priya", "text": "take the design", "type": "explicit"}], [],
        ["design", "code", "split"], ["budget", "lawsuit"])

    add("conv-017", "Morgan",
        ["ambiguous_pronouns", "explicit_commitments"],
        [{"speaker": "Morgan", "text": "She said she'd handle it."}, {"speaker": "You", "text": "Who?"}, {"speaker": "Morgan", "text": "Lena. She will send the proposal by Thursday."}],
        [{"entity": "Lena", "text": "I will send the proposal", "signal_type": "commitment_made", "timestamp": "2026-07-01T10:00:00Z"}],
        [{"entity": "Lena", "text": "send the proposal by Thursday", "type": "explicit"}], [],
        ["Lena", "proposal", "Thursday"], ["budget", "lawsuit"])

    add("conv-018", "Avery",
        ["incomplete_sentences", "interruptions"],
        [{"speaker": "Avery", "text": "I was going to say that the migra—"}, {"speaker": "You", "text": "Is it done?"}, {"speaker": "Avery", "text": "Not yet. But I will finish the migration by end of week."}],
        [{"entity": "Avery", "text": "I will complete the migration", "signal_type": "commitment_made", "timestamp": "2026-07-02T10:00:00Z"}],
        [{"entity": "Avery", "text": "finish the migration by end of week", "type": "explicit"}], [],
        ["migration", "end of week"], ["budget", "report"])

    add("conv-019", "Marco",
        ["disagreement", "negotiation_anchors"],
        [{"speaker": "Marco", "text": "I disagree with the $50k price. My anchor is $70k."}, {"speaker": "You", "text": "Let's meet in the middle."}, {"speaker": "Marco", "text": "$60k, but only if you commit to a 2-year deal."}],
        [{"entity": "Marco", "text": "I will send the pricing", "signal_type": "commitment_made", "timestamp": "2026-07-03T10:00:00Z"}],
        [], [], ["70k", "60k", "anchor"], ["budget", "report"])

    add("conv-020", "Yuki",
        ["revoked_commitments", "sarcasm"],
        [{"speaker": "Yuki", "text": "Oh, the old plan? Yeah, that's totally happening. Not."}, {"speaker": "You", "text": "So it's cancelled?"}, {"speaker": "Yuki", "text": "Yes, the old plan is revoked. I can't do it."}],
        [{"entity": "Yuki", "text": "I will deliver the old plan", "signal_type": "commitment_made", "timestamp": "2026-07-04T10:00:00Z"}],
        [], [{"entity": "Yuki", "text": "old plan is revoked", "type": "revoked"}],
        ["revoked", "old plan"], ["budget", "contract"])

    # 21-30: Remaining feature combinations
    add("conv-021", "David",
        ["explicit_commitments", "concessions"],
        [{"speaker": "David", "text": "I will send the contract by Monday, and I'll throw in the appendix for free as a concession."}],
        [{"entity": "David", "text": "I will send the contract", "signal_type": "commitment_made", "timestamp": "2026-07-05T10:00:00Z"}],
        [{"entity": "David", "text": "send the contract by Monday", "type": "explicit"}], [],
        ["contract", "Monday", "appendix"], ["budget", "report"])

    add("conv-022", "Lena",
        ["filler", "incomplete_sentences"],
        [{"speaker": "Lena", "text": "So, um, I was thinking about the, you know, the thing with the..."}, {"speaker": "You", "text": "The proposal?"}, {"speaker": "Lena", "text": "Right. I'll send it by, uh, soon."}],
        [{"entity": "Lena", "text": "I will send the proposal", "signal_type": "commitment_made", "timestamp": "2026-07-06T10:00:00Z"}],
        [], [], ["proposal"], ["budget", "lawsuit"])

    add("conv-023", "Raj",
        ["corrections", "explicit_commitments"],
        [{"speaker": "Raj", "text": "I said Wednesday, but correction — I will send the report by Thursday instead."}],
        [{"entity": "Raj", "text": "I will send the report", "signal_type": "commitment_made", "timestamp": "2026-07-07T10:00:00Z"}],
        [{"entity": "Raj", "text": "send the report by Thursday", "type": "explicit"}], [],
        ["Thursday", "correction"], ["budget", "lawsuit"])

    add("conv-024", "Alex",
        ["interruptions", "filler"],
        [{"speaker": "Alex", "text": "I'll, um—"}, {"speaker": "You", "text": "Spit it out."}, {"speaker": "Alex", "text": "Sorry. I will send the budget by Friday."}],
        [{"entity": "Alex", "text": "I will send the budget", "signal_type": "commitment_made", "timestamp": "2026-07-08T10:00:00Z"}],
        [{"entity": "Alex", "text": "send the budget by Friday", "type": "explicit"}], [],
        ["budget", "Friday"], ["lawsuit", "contract"])

    add("conv-025", "Maria",
        ["sarcasm", "tentative_statements"],
        [{"speaker": "Maria", "text": "Oh sure, I'll definitely have it ready. Maybe. If the stars align."}],
        [{"entity": "Maria", "text": "I will send the report", "signal_type": "commitment_made", "timestamp": "2026-07-09T10:00:00Z"}],
        [], [], ["tentative"], ["budget", "contract"])

    add("conv-026", "Sam",
        ["changed_positions", "negotiation_anchors"],
        [{"speaker": "Sam", "text": "I was at $80k, but I've changed my position. New anchor: $95k."}],
        [{"entity": "Sam", "text": "I will send the pricing", "signal_type": "commitment_made", "timestamp": "2026-07-10T10:00:00Z"}],
        [], [], ["95k", "anchor"], ["budget", "report"])

    add("conv-027", "Priya",
        ["multiple_speakers", "disagreement"],
        [{"speaker": "Priya", "text": "I think we should go with Option A."}, {"speaker": "Morgan", "text": "I disagree. Option B is better."}, {"speaker": "Priya", "text": "Fine, let's vote."}],
        [{"entity": "Priya", "text": "I will choose the option", "signal_type": "commitment_made", "timestamp": "2026-07-11T10:00:00Z"}],
        [], [], ["Option A", "Option B", "disagree"], ["budget", "lawsuit"])

    add("conv-028", "Morgan",
        ["ambiguous_pronouns", "revoked_commitments"],
        [{"speaker": "Morgan", "text": "He backed out."}, {"speaker": "You", "text": "Who?"}, {"speaker": "Morgan", "text": "David. He cancelled the contract commitment."}],
        [{"entity": "David", "text": "I will send the contract", "signal_type": "commitment_made", "timestamp": "2026-07-12T10:00:00Z"}],
        [], [{"entity": "David", "text": "cancelled the contract commitment", "type": "revoked"}],
        ["David", "cancelled", "contract"], ["budget", "report"])

    add("conv-029", "Avery",
        ["concessions", "explicit_commitments"],
        [{"speaker": "Avery", "text": "I'll concede the timeline — one week instead of two. And I will finish the migration by next Friday."}],
        [{"entity": "Avery", "text": "I will complete the migration", "signal_type": "commitment_made", "timestamp": "2026-07-13T10:00:00Z"}],
        [{"entity": "Avery", "text": "finish the migration by next Friday", "type": "explicit"}], [],
        ["migration", "Friday", "concession"], ["budget", "lawsuit"])

    add("conv-030", "Marco",
        ["disagreement", "corrections"],
        [{"speaker": "Marco", "text": "I disagree with the timeline. And actually, correction — I said I'd send the audit, but I meant the report."}],
        [{"entity": "Marco", "text": "I will send the security audit", "signal_type": "commitment_made", "timestamp": "2026-07-14T10:00:00Z"}],
        [], [], ["report", "correction", "disagree"], ["budget", "contract"])

    return convs


CONVERSATIONS: list[dict[str, Any]] = _build_conversations()


def get_copilot_benchmark() -> list[dict[str, Any]]:
    """Return the 30-conversation Copilot benchmark."""
    return CONVERSATIONS


def get_benchmark_stats() -> dict[str, int]:
    """Return per-feature counts."""
    stats: dict[str, int] = {}
    for c in CONVERSATIONS:
        for f in c.get("features", []):
            stats[f] = stats.get(f, 0) + 1
    return stats


def get_all_features() -> set[str]:
    """Return all 14 roadmap features."""
    all_features = set()
    for c in CONVERSATIONS:
        all_features.update(c.get("features", []))
    return all_features


if __name__ == "__main__":
    convs = get_copilot_benchmark()
    print(f"Total conversations: {len(convs)}")
    print(f"Features covered: {len(get_all_features())}")
    for f, count in sorted(get_benchmark_stats().items()):
        print(f"  {f:30s} {count}")
    print(f"\nAll 14 features covered: {len(get_all_features()) == 14}")
