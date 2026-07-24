# Prateek's Operational Steps to 🟢

The coder has closed everything closable from the sandbox. The backend is at 🟢 quality with a 29/29 auto-running gate. The two remaining steps to move the band to 🟢 are operational and require your Railway dashboard access + a Yahoo Developer account. This guide walks through each.

## Step 1: Wire the Frontend to Auto-Deploy from `main` (unblocks the UI gate)

### The problem
The backend (`maestroagent-production.up.railway.app`) auto-deploys from GitHub `main` via a repo trigger. The frontend (`web-production-d5c26.up.railway.app`) does **not** — it was deployed manually in a prior cycle and has no repo trigger. This means:
- The UI gate (19 Playwright assertions) is currently **skipping loudly** because the frontend doesn't have the latest code (the 4-tab IA redesign with "Today" / "My sources" / "Demo inbox").
- A frontend regression could ship undetected because the gate can't run.

### The fix

1. **Find the frontend service.** The frontend URL is `web-production-d5c26.up.railway.app`. The coder's token can only see the `brilliant-vision` project (services: MaestroAgent, alert-essence, amiable-optimism) — **none of those own the `web-production-d5c26` domain**. The frontend is in a different Railway workspace or project. Check your Railway dashboard for all workspaces/teams you're part of, and find the service with the `web-production-d5c26.up.railway.app` domain binding.

2. **Wire the repo trigger.** Once you've found the frontend service:
   - Go to the service's **Settings** tab
   - Find the **GitHub integration** / **Repo Trigger** section
   - Connect it to `prateekm1007/MaestroAgent` on the `main` branch
   - Set the **Root Directory** to `download/MaestroAgent/maestro-personal/web` (this is critical — without it, Railway will try to build from the repo root and fail, which is what happened with the `alert-essence` service)
   - Save

3. **Deploy from latest `main`.** Trigger a manual deploy from the latest `main` commit (`768ac29` or later). The build should use the `Dockerfile` in `maestro-personal/web/` (Next.js standalone output).

4. **Verify.** Once deployed, the frontend should have:
   - Title: "Maestro — Today" (not "Maestro — Personal Intelligence")
   - Nav: 4 tabs (Today / Ask / Commitments / More) — not 7 tabs
   - More tab: 5 sub-sections (Connectors / My sources / Demo inbox / Agent controls / Settings)

5. **Confirm the UI gate runs.** Once the frontend deploys, push any commit to `main`. The CI workflow will run both gates:
   - `permanence-gate` (backend, 29/29) — should be green
   - `ui-gate` (frontend, 19 assertions) — should now run (not skip) and pass

### Cleanup
The `alert-essence` service in the `brilliant-vision` project is a broken duplicate backend (the coder's failed `railway up` attempt). You can delete it — it serves no purpose.

---

## Step 2: Yahoo Mail One-Click OAuth (verifies precondition 3)

### The problem
The Yahoo Mail OAuth connector is **built** (`yahoo_mail_connector.py`, 13.7KB — OAuth flow, token exchange, refresh, ingestion all implemented), but it has not been **verified end-to-end**. "Built ≠ verified" is the distinction the auditor (correctly) holds.

### The fix

1. **Create a Yahoo Developer Portal app.**
   - Go to https://developer.yahoo.com/apps/create/
   - Create a new app
   - Set the **Redirect URI** to: `https://maestroagent-production.up.railway.app/api/connectors/yahoo_mail/oauth/callback`
   - Select the **mail-ro** scope (read-only mail access)
   - Note the **Client ID** and **Client Secret**

2. **Set the env vars on Railway.** On the **backend** service (`MaestroAgent`, `c12adfcf`), add:
   ```
   MAESTRO_YAHOO_CLIENT_ID=<your Yahoo app client ID>
   MAESTRO_YAHOO_CLIENT_SECRET=<your Yahoo app client secret>
   MAESTRO_YAHOO_REDIRECT_URI=https://maestroagent-production.up.railway.app/api/connectors/yahoo_mail/oauth/callback
   ```
   The backend will auto-redeploy when these are set.

3. **Connect a real Yahoo account.**
   - Open the frontend (once deployed from Step 1)
   - Navigate to **More → Connectors**
   - Click the **Yahoo Mail** card
   - A Yahoo OAuth consent popup should open
   - Log in with a real Yahoo account + grant consent
   - You should be redirected back and see "Yahoo Mail Connected!"
   - **No app password required** — this is the one-click OAuth flow

4. **Verify real signals arrive.**
   - Click "Sync now" on the Yahoo Mail connector
   - Navigate to **More → My sources** — you should see signals with `source: yahoo`
   - Navigate to **Commitments** — any commitments extracted from Yahoo Mail should appear
   - Try an Ask query: "What did I promise [person from your Yahoo Mail]?"

5. **Confirm the Glean standard is met.** The auditor's precondition 3 is: "Yahoo connects in one click, no app password." Once you've done the above, that's verified end-to-end.

---

## Step 3: Google Calendar `calendar.readonly` scope (unchanged)

### The problem
The Calendar OAuth connector reuses the Gmail OAuth client. The Gmail client has `gmail.readonly` + `gmail.send` scopes but NOT `calendar.readonly`. So when a user tries to connect Calendar, Google rejects the scope mismatch.

### The fix

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → OAuth consent screen
2. Find your Maestro OAuth client (the one with `MAESTRO_GMAIL_CLIENT_ID`)
3. Add the scope: `https://www.googleapis.com/auth/calendar.readonly`
4. Save

5. Verify the redirect URI is whitelisted:
   - The Calendar connector uses the SAME redirect URI as Gmail: `https://maestroagent-production.up.railway.app/api/connectors/gmail/oauth/callback`
   - This should already be whitelisted (it's the Gmail callback)
   - If you see a `redirect_uri_mismatch` error, add the URI to the authorized redirect URIs list

6. Test: open the frontend → More → Connectors → click Google Calendar → consent → connected

---

## After all 3 steps

Once you've completed:
- ✅ Step 1: Frontend auto-deploys from `main` → UI gate runs (19 assertions)
- ✅ Step 2: Yahoo OAuth verified with real signals (`source: yahoo`)
- ✅ Step 3: Calendar scope added → Calendar connects

Then:
- Both gates run green end-to-end in CI on every push
- All 3 🟢 preconditions are met
- The band moves to 🟢 (Strong Product — Ready for limited beta)
- The next gate is ✅ (full external re-audit: OAuth revoke/reconnect, offline/expired-token recovery, 50+ pre-registered cases, production telemetry)

The coder has done everything else. These three steps are the last stones.
