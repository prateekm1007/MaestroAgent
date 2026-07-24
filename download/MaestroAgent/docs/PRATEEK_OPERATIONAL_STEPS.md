# Prateek's Operational Steps — Connectors First, Then Everything Else

> **Reoriented 2026-07-24** per auditor instruction: "Gmail diagnosis/fix first, then Calendar scope, then Yahoo OAuth, then frontend deploy."

## Connector Diagnosis (completed by coder, 2026-07-24)

The coder ran a full Trace-Before-Fix diagnosis against live state. Results:

| Connector | State | Root cause | Action needed |
|---|---|---|---|
| **Gmail** | ✅ WORKING | 49 emails, 56 commitments, sync succeeds | None — verified end-to-end |
| **Calendar** | ⚠️ Connected but 0 events | Missing `calendar.readonly` scope | **Step 1** (Prateek) |
| **Work email** | Not connected | User hasn't provided IMAP creds | Optional — Step 3 |
| **Yahoo** | Not configured | `MAESTRO_YAHOO_CLIENT_ID` not set | **Step 2** (Prateek) |
| **Microsoft** | Not configured | `MAESTRO_MICROSOFT_CLIENT_ID` not set | Step 2 (same pattern) |
| **Frontend** | Stale | Not deployed with latest code | **Step 4** (Prateek) |

**Key finding:** Gmail IS working. The backend infrastructure is functional end-to-end. The connector issues are operational, not code bugs.

**The gate now covers connectors:** `[CONN]` assertions (5 new) verify Gmail is connected + sync completes + messages returned on every push. If Gmail breaks, the gate fails. Connectors can no longer break silently.

---

## Step 1: Google Calendar `calendar.readonly` scope (fixes Calendar connector)

### The problem
Calendar shows `connected=True` but `commitments_ingested=0` and `last_ingest=(empty)`. The Calendar OAuth reuses the Gmail client, which has `gmail.readonly` + `gmail.send` but NOT `calendar.readonly`. So when the Calendar API is called, Google rejects it.

### The fix
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → OAuth consent screen
2. Find your Maestro OAuth client (Client ID: `719625682041-...`)
3. Add the scope: `https://www.googleapis.com/auth/calendar.readonly`
4. Save
5. Test: open the frontend → More → Connectors → click Google Calendar → consent → connected → Sync now → should return events

---

## Step 2: Yahoo Mail + Microsoft Mail OAuth setup (verifies precondition 3)

### Yahoo
1. Go to https://developer.yahoo.com/apps/create/
2. Create a new app with the **mail-ro** scope
3. Set the Redirect URI to: `https://maestroagent-production.up.railway.app/api/connectors/yahoo_mail/oauth/callback`
4. Note the Client ID + Client Secret
5. On Railway (backend service `MaestroAgent`), set:
   ```
   MAESTRO_YAHOO_CLIENT_ID=<your Yahoo app client ID>
   MAESTRO_YAHOO_CLIENT_SECRET=<your Yahoo app client secret>
   MAESTRO_YAHOO_REDIRECT_URI=https://maestroagent-production.up.railway.app/api/connectors/yahoo_mail/oauth/callback
   ```
6. Connect a real Yahoo account via More → Connectors → Yahoo Mail (one-click, no app password)
7. Verify real signals arrive with `source: yahoo` in More → My sources

### Microsoft
Same pattern:
1. Go to Azure Portal → App Registrations → New registration
2. Add API permissions: `Mail.Read`, `Mail.Send`, `offline_access`, `openid`, `email`, `profile`
3. Set Redirect URI to: `https://maestroagent-production.up.railway.app/api/connectors/microsoft_mail/oauth/callback`
4. Set env vars on Railway:
   ```
   MAESTRO_MICROSOFT_CLIENT_ID=<your Azure app client ID>
   MAESTRO_MICROSOFT_CLIENT_SECRET=<your Azure app client secret>
   MAESTRO_MICROSOFT_TENANT_ID=common
   MAESTRO_MICROSOFT_REDIRECT_URI=https://maestroagent-production.up.railway.app/api/connectors/microsoft_mail/oauth/callback
   ```
5. Connect via More → Connectors → Microsoft 365 / Outlook

---

## Step 3: Work Email (optional — IMAP)

Work email uses direct IMAP credentials (not OAuth). To connect:
1. Open More → Connectors → Work Email (Advanced)
2. Enter your work email address (IMAP host auto-detected)
3. Enter an app password (NOT your regular password — generate one in your email provider's security settings)
4. Click Connect & Verify

This is the "Advanced" path for providers without OAuth (ProtonMail Bridge, custom domains). For Gmail/Outlook/Yahoo, use the one-click OAuth cards instead.

---

## Step 4: Wire the Frontend to Auto-Deploy from `main` (unblocks the UI gate)

### The problem
The backend auto-deploys from GitHub `main`. The frontend does NOT — it was deployed manually and is stale (missing the 4-tab IA redesign, MySources, calibration callout, etc.). The UI gate skips loudly because the frontend doesn't have the latest code.

### The fix
1. **Find the frontend service.** The frontend URL is `web-production-d5c26.up.railway.app`. The coder's token can only see the `brilliant-vision` project — the frontend is in a different Railway workspace. Check your Railway dashboard for all workspaces.
2. **Wire the repo trigger.** On the frontend service: Settings → GitHub integration → connect to `prateekm1007/MaestroAgent` on `main` branch. Set the **Root Directory** to `download/MaestroAgent/maestro-personal/web` (critical — without it, Railway builds from the repo root and fails).
3. **Deploy from latest `main`.** Trigger a manual deploy from the latest `main` commit.
4. **Verify:** Title should be "Maestro — Today", nav should have 4 tabs (Today/Ask/Commitments/More), More should have 5 sub-sections.
5. **Cleanup:** Delete the `alert-essence` service in `brilliant-vision` — it's a broken duplicate backend from a failed `railway up`.

---

## After all 4 steps

- Gmail: working + gated (`[CONN]` assertions)
- Calendar: working (scope added)
- Yahoo: one-click OAuth verified with real signals
- Microsoft: one-click OAuth verified
- Frontend: auto-deploys from main, UI gate runs 19 assertions
- Gate: 34/34 backend + 19 UI = 53 assertions, all green, auto-running on every push

The band moves to 🟢. The next gate is ✅ (full external re-audit).
