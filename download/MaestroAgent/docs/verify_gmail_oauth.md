# Gmail OAuth End-to-End Verification

**Ticket**: VERIFY: Real Gmail OAuth end-to-end (issue #6)
**Date verified**: 2026-07-27
**Author**: Build agent (GLM) — P47 honest attribution

## Summary

Gmail OAuth **IS connected and working** on the production demo account. Real emails **ARE being synced** (50 emails, 54 real Gmail signals). However, the **commitment extraction from real emails is poor quality** — the 5 "commitments" extracted from real Gmail are **false positives** from marketing/newsletter emails, not actual commitments.

**Verdict: PARTIAL** — Gmail sync works end-to-end, but the commitment extraction quality from real emails does not match the investor briefing's claim of "29 commitments found" with "58% extraction rate."

---

## Date

2026-07-27 (post-deploy, production commit `44a3e70`)

## Account used

- **Demo account**: `default@personal.local` (bootstrap account on production)
- **Gmail connected**: `true` since 2026-07-26T08:21:32
- **Last ingest**: 2026-07-27T04:36:13 (triggered during this verification)

## Connection method

**Existing connection** — Gmail was already connected to the demo account via OAuth (connected_at: 2026-07-26T08:21:32). The `oauth_configured: true` flag on the connectors endpoint confirms Gmail OAuth credentials are set on Railway. No manual consent step was needed — the connection was established in a prior session.

## Emails synced

- **This sync**: 50 emails ingested (9 new commitments, 41 duplicates from prior syncs)
- **Total real Gmail signals**: 54 (signal IDs starting with `conn_gmail_`)
- **Response from POST /api/connectors/gmail/ingest**:
  ```json
  {
    "provider": "gmail",
    "ingested": 50,
    "new_commitments": 9,
    "duplicates": 41,
    "ingested_at": "2026-07-27T04:36:13.938128+00:00"
  }
  ```

## Real email signals

- **Count**: 54 signals with `source_type` = Gmail (signal IDs: `conn_gmail_*`)
- **Unique entities**: 25 real senders including:
  - Slack, Cursor Team, ngrok, Samsung Electronics India, The Washington Post
  - Kotak Bank, KotakSecurities, PayPal, Reddit, Railway
  - Chess.com, DSIJ Editorial, Dalal Street Investment Journal
  - F.A. Hayek (Facebook), Polsia, and others
- **These are REAL emails** — marketing newsletters, bank notifications, product updates, social media notifications. NOT synthetic demo data.

## Commitments extracted

- **Count**: 5 commitments from real Gmail signals
- **Extraction rate**: 5/50 = **10%** (not 58% as claimed in investor briefing)
- **Quality**: **POOR — all 5 are false positives**

### The 5 "commitments" from real Gmail

| # | Entity | Text | Assessment |
|---|--------|------|------------|
| 1 | Kotak Bank | "Important Update Scheduled Downtime Dear Customer..." | **False positive** — bank notification, not a commitment |
| 2 | Reddit | "r/opencode: OPENCODE NEW VERSION I just updated..." | **False positive** — Reddit notification |
| 3 | F.A. Hayek (Facebook) | "See what he posted. Richard Ebeling posted..." | **False positive** — Facebook notification |
| 4 | KotakSecurities | "Dear Customer, With reference to your Trading..." | **False positive** — securities account notification |
| 5 | Railway | "It's Friday and you know what that means!..." | **False positive** — product newsletter |

**None of the 5 "commitments" are actual commitments.** They are marketing emails and notifications that contain phrases like "I will" or "we will" in marketing copy context, which the classifier incorrectly flagged as commitments.

## Sample question and answer

**Question**: "What did I promise Slack?"

**Answer**:
> Regarding your question about promises:
> Based on the situation for Slack, the key commitment is: Slack: I will conquer the moon haha
> State: observing

**Evidence refs**: 2, both from real Gmail signals:
- `conn_gmail_3f87a050`: "Move your next project into a channel..." (Slack marketing email)
- `conn_gmail_09b669ac`: "Get more done when your team has one place..." (Slack marketing email)

**Intelligence source**: `rules`

**Assessment**: The answer references a real Gmail signal, but the "commitment" ("I will conquer the moon haha") is a marketing tagline from a Slack email, not an actual commitment made by the user. This demonstrates that the commitment classifier misclassifies marketing email copy as first-person commitments.

## Evidence source verification

- **Real Gmail signals used as evidence**: YES — the ask endpoint returned evidence with `conn_gmail_*` signal IDs
- **Synthetic signals also present**: YES — 60 signals with `synthetic_email_*` IDs (from the synthetic inbox demo)
- **The ask endpoint correctly retrieves real Gmail signals**: YES — the evidence_refs contain `conn_gmail_*` IDs, proving the Gmail connector's data flows into the ask pipeline
- **But the commitment extraction is wrong**: The classifier flags marketing copy ("I will conquer the moon haha") as a user commitment

## Verdict

### **PARTIAL**

**What works** ✅:
- Gmail OAuth connection is established and persistent
- Email ingestion syncs real emails (50 emails, 54 signals)
- Real Gmail signals flow into the ask pipeline as evidence
- The connector infrastructure is functional end-to-end

**What doesn't work** ❌:
- Commitment extraction from real emails produces false positives
- 5/5 "commitments" from real Gmail are marketing/newsletter emails misclassified as commitments
- The extraction rate is 10% (5/50), not 58% as claimed
- The "29 commitments found" claim in the investor briefing is **NOT supported** by this verification

## Investor briefing claim assessment

| Claim | Source | Verified? | Actual |
|-------|--------|-----------|--------|
| "Gmail OAuth is verified working end-to-end" | Page 9 | **YES** | Gmail connected, 50 emails synced |
| "50 emails synced" | Page 9 | **YES** | 50 emails ingested |
| "29 commitments found" | Page 9 | **NO** | 5 commitments (all false positives) |
| "Real Gmail sync, not synthetic" | Page 12 | **YES** | 54 real Gmail signals present |
| "Commitments extracted: 29" | Page 12 | **NO** | 5 extracted (not 29) |
| "58% extraction rate" | Page 12 | **NO** | 10% extraction rate (5/50) |

### Honest assessment

The investor briefing **overstates** the commitment extraction quality. While Gmail sync works and real emails are ingested, the classifier produces false positives on marketing emails. The "29 commitments" and "58% extraction rate" claims are not reproducible from the current real Gmail data.

**Recommendation**: Update the investor briefing to:
- "Gmail OAuth verified working: 50 real emails synced"
- "Commitment extraction from real emails: 5 extracted (quality issue — false positives on marketing copy)"
- Remove the "29 commitments" and "58% extraction rate" claims until the classifier is improved

## Follow-up actions

1. **TICKET-6b (recommended)**: Improve commitment classifier to reject marketing/newsletter emails. The classifier should distinguish between:
   - First-person commitments in personal/work emails ("I will send the proposal by Friday")
   - Marketing copy that uses "I will" or "we will" ("I will conquer the moon haha")
   
2. **Update investor briefing**: Soften the "29 commitments / 58% extraction rate" claim to reflect the actual 5 commitments / 10% rate, or remove it until the classifier improves.

3. **Add a marketing-email filter**: Signals from known marketing senders (Slack, Cursor, newsletters) should be classified as `signal_type: marketing` not `commitment_made`, and excluded from commitment extraction.

## Principle compliance

- **P47 (honest attribution)**: This verification documents both what works (Gmail sync) and what doesn't (commitment extraction quality). No claims are fabricated.
- **FA27 (no verdict without reproduction)**: The verdict is backed by live reproduction against production — real API calls, real Gmail signals, real evidence refs.
- **P68 (regression test beats governance prose)**: The verifier recommends a follow-up ticket for the classifier improvement, not just documentation.

## Verification metadata

- **Production commit**: `44a3e70`
- **Test account**: `default@personal.local` (demo, with Gmail connected since 2026-07-26)
- **Ingest timestamp**: 2026-07-27T04:36:13
- **Total signals on demo account**: 165 (54 real Gmail + 60 synthetic + 51 other)
- **Real Gmail entities**: 25 unique senders
