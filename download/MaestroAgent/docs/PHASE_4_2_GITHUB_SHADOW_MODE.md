# Phase 4.2 — GitHub Shadow Mode Setup Guide

## What shadow mode does

Shadow mode lets you connect a real GitHub account and ingest real signals
(PR opens, merges, commits, reviews) through the full pipeline — WITHOUT
surfacing them to users. This verifies the connector works end-to-end
before you flip to live mode.

**What happens in shadow mode:**
- Real GitHub signals are ingested (the OEM engine processes them)
- Signals are marked `metadata["shadow"] = True`
- Shadow signals are filtered out of: whispers, CEO briefing, Ask answers
- A debug endpoint (`GET /api/oem/shadow-signals`) lets you inspect them

**What does NOT happen in shadow mode:**
- No whispers fire (shadow signals are invisible to the whisper pipeline)
- No briefing cards show shadow data
- No Ask answers reference shadow signals

## Setup steps

### 1. Create a GitHub OAuth App

1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - **Application name:** MaestroAgent Shadow Mode
   - **Homepage URL:** `http://localhost:1420` (or your shadow host)
   - **Authorization callback URL:** `http://localhost:1420/api/oauth/callback`
4. Click "Register application"
5. Copy the **Client ID**
6. Click "Generate a new client secret" → copy the **Client Secret** (you won't see it again)

### 2. Set environment variables

```bash
# GitHub OAuth credentials
export MAESTRO_OAUTH_GITHUB_CLIENT_ID="your_client_id"
export MAESTRO_OAUTH_GITHUB_CLIENT_SECRET="your_client_secret"
export MAESTRO_OAUTH_REDIRECT_URI="http://localhost:1420/api/oauth/callback"

# Shadow mode ON (signals ingested but NOT surfaced)
export MAESTRO_SHADOW_MODE=true

# Demo seed OFF (don't contaminate real data with acme-corp fixtures)
export MAESTRO_DEMO_SEED=false

# Local dev (auth defaults off for easier testing)
export MAESTRO_LOCAL_DEV=true
```

### 3. Start the backend

```bash
cd backend
make dev-backend
# OR
python -m uvicorn maestro_api.main:create_app --factory --host 127.0.0.1 --port 1420
```

### 4. Connect GitHub

Open the app in your browser:
1. Navigate to Settings → Connect a source
2. Click "Connect GitHub"
3. Authorize the OAuth app on GitHub
4. You'll be redirected back — the connection is now active

The historical import starts automatically (5 years of history by default).

### 5. Verify shadow signals

```bash
# Check shadow mode is active
curl http://localhost:1420/api/oem/state | python -m json.tool | grep shadow_mode

# Inspect shadow signals (the real GitHub data flowing in)
curl http://localhost:1420/api/oem/shadow-signals?limit=10 | python -m json.tool
```

You should see:
- `"shadow_mode": true` in the state response
- Real GitHub PR/commit/issue signals in the shadow-signals response
- `"shadow": true` in each signal's metadata

### 6. Verify shadow signals are NOT surfaced

```bash
# The CEO briefing should NOT reference any GitHub shadow signals
curl http://localhost:1420/api/oem/ceo-briefing | python -m json.tool

# Whispers should NOT fire from shadow signals
curl http://localhost:1420/api/oem/whisper | python -m json.tool

# Ask should NOT reference shadow signals
curl -X POST http://localhost:1420/api/oem/ask/conversation \
  -H "Content-Type: application/json" \
  -d '{"query": "What did we ship recently?", "session_id": "shadow-test"}'
```

If any of these reference GitHub data, shadow mode is broken.

### 7. Flip to live mode

Once you've verified the pipeline works:

```bash
# Turn off shadow mode
export MAESTRO_SHADOW_MODE=false

# Restart the backend
# Existing shadow signals stay in the DB but are now surfaced
# (they lose their shadow flag on the next ingest cycle)
```

## Troubleshooting

**"No refresh token for github" error:** GitHub OAuth Apps don't issue
refresh tokens. This is expected — GitHub tokens live until revoked. If
a token is revoked, disconnect and reconnect.

**Import pulls from ALL repos, not just my org:** This was a bug (fixed
in this commit). The historical engine now passes `org_id` to the GitHub
fetcher, which scopes to `/orgs/{org}/repos`. Make sure your GitHub
account is a member of the org you want to import from.

**Shadow signals appear in whispers:** This would be a bug. The whisper
pipeline filters shadow signals in `whisper.py:__init__`. If you see
shadow data in whispers, check that the filter is working:
```python
# In whisper.py __init__:
self.signals = [
    s for s in (signals or [])
    if not (hasattr(s, "metadata") and s.metadata and s.metadata.get("shadow"))
]
```

## Security notes

- GitHub access tokens are stored in SQLite (`oauth_credentials` table).
  They are NOT encrypted at rest (unlike client secrets, which use
  AES-256-GCM). For production, consider encrypting access tokens too.
- The OAuth state token is HMAC-signed with `JWT_SECRET`. Set a strong
  `JWT_SECRET` in production (the default is dev-only).
- Disconnecting revokes the GitHub token via `DELETE /applications/{id}/token`.
  Already-ingested signals are NOT deleted (they're historical fact).
