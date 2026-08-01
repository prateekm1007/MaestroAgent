# Strategic Decision: Unified Connector API vs Per-Provider OAuth

> **Sean Parker reframe (2026-07-24):** "Don't build it, leverage it." The per-provider OAuth treadmill (create a Yahoo app, create an Azure app, create a Google app, maintain each, handle token refresh for each) is the wrong architecture for a million-user vision. A unified connector API eliminates the treadmill entirely.

## The two paths

### Path A: Per-Provider OAuth (current — fine for pilot, wrong for scale)

**How it works:** Maestro creates a developer app at each provider (Google, Microsoft, Yahoo, ...), stores the client ID/secret as env vars, and implements the OAuth flow + token refresh + API calls for each provider individually.

**Pros:**
- No vendor dependency — direct integration with each provider
- No per-user cost (no third-party metering)
- Full control over data routing (data flows directly from provider → Maestro, no intermediary)
- Aligns with the `/api/privacy/mode` posture (no third-party data routing)

**Cons:**
- Per-provider app creation is a human-gated step (ToS, review, redirect-URI whitelisting) that can't be scripted
- Each provider has different OAuth quirks, token refresh logic, API shapes
- Adding a new provider = a new developer app + new connector code + new env vars
- Doesn't scale beyond ~5-6 providers before the maintenance burden is unsustainable
- No coverage for providers without OAuth (IMAP-only, custom domains, legacy Exchange)

**When to choose:** Pilot phase (3-4 providers), privacy-critical customers who require direct integration, early stage where vendor cost matters.

### Path B: Unified Connector API (the scale move)

**How it works:** Integrate ONE unified connector API (Nylas, Paragon, Unified.to, or similar). The aggregator handles OAuth + token refresh + API normalization across dozens of providers. Maestro builds ONE integration against the aggregator; users connect ANY provider through the aggregator's hosted OAuth.

**Pros:**
- **One integration, fifty+ providers** — Gmail, Outlook, Yahoo, iCloud, IMAP, Exchange, calendars, CRMs, contacts, all under one OAuth app
- **Zero per-provider developer apps** — the aggregator has already done the app creation + review + maintenance
- **Hosted OAuth** — the aggregator handles the consent screen, token storage, and refresh; Maestro never touches raw OAuth tokens
- **Normalized API** — one data shape for "email" or "calendar event" across all providers
- **Instant provider coverage** — adding a new provider is a config change, not a code change
- **Sean Parker leverage** — the founder creates ONE app (the aggregator integration), and the product supports FIFTY providers forever

**Cons:**
- Vendor dependency — if the aggregator goes down, all connectors go down
- Per-user cost — aggregators charge per connected account (typically $0.10-$5/user/month depending on provider + volume)
- Third-party data routing — data flows provider → aggregator → Maestro (the aggregator sees the data)
- May conflict with the `/api/privacy/mode` posture for privacy-critical customers

**When to choose:** Scale phase (50+ providers, self-serve beta, million-user vision), when vendor cost is acceptable, when the privacy posture allows third-party routing.

## The aggregator options (as of 2026-07)

| Aggregator | Focus | Pricing model | Notable |
|---|---|---|---|
| **Nylas** | Email + calendar + contacts | Per connected account | Most mature, best provider coverage for email |
| **Paragon** | Workflow + connector embed | Per user + per connector | Best for embedded connector UI |
| **Unified.to** | Unified API across 50+ SaaS | Per connected account | Broadest coverage (CRM, ticketing, etc.) |
| **RudderStack** | Customer data + connectors | Event-based | Different focus (analytics, not email) |

For Maestro's use case (email + calendar commitments), **Nylas** is the strongest fit — they specialize in email/calendar, have the deepest provider coverage, and their hosted OAuth means Maestro never touches raw tokens.

## The recommendation

**Ship Path A for the pilot (this week).** The per-provider OAuth is already built (Gmail works, Yahoo/Microsoft connectors exist). Prateek's one-time action (create Yahoo + Azure apps, paste creds into `ops/provision_connector.py`) gets the pilot live with 3-4 providers in under an hour. This unblocks the beta.

**Evaluate Path B for scale (next 2-4 weeks).** Once the pilot is live and the activation funnel is measured, evaluate Nylas (or similar) as the scale architecture. The decision criteria:
- If the pilot shows users want connectors beyond Gmail/Outlook/Yahoo → Path B
- If the per-provider maintenance burden grows → Path B
- If privacy-critical customers require direct integration → stay Path A
- If vendor cost is acceptable at projected volume → Path B

**The architectural decision is Prateek's to make deliberately, not by drift.** The current code (Path A) is correct for the pilot; Path B is the scale move that eliminates the per-provider treadmill forever.

## What changes if Path B is chosen

1. Replace `yahoo_mail_connector.py`, `microsoft_mail_connector.py`, `gmail_connector.py`, `calendar_connector.py` with a single `nylas_connector.py`
2. Set `MAESTRO_NYLAS_API_KEY` + `MAESTRO_NYLAS_CLIENT_ID` + `MAESTRO_NYLAS_CLIENT_SECRET` as env vars (ONE set, not per-provider)
3. The Connectors page shows ONE "Connect your email" card that routes through Nylas hosted OAuth
4. The `[CONN]` gate assertion tests the Nylas integration (one assertion covers all providers)
5. The `ops/provision_connector.py` script becomes a one-time Nylas setup (create Nylas account, paste API key)

**The founder's one-time action shrinks from "create N apps at N consoles" to "create one Nylas account."** That's the true Sean Parker leverage.
