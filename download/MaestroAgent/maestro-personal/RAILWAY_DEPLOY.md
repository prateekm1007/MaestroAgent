# Railway Deployment Guide — MaestroAgent

Deploy the full app (backend + web) to Railway in ~10 minutes.
After deployment, you'll have two public URLs that work from any browser or phone.

## Prerequisites

- Railway account (you have a 30-day trial)
- GitHub repo: `prateekm1007/MaestroAgent`
- An LLM API key (ZAI is free + already configured; OpenAI optional for higher quality)

## Step 1: Deploy the Backend

1. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
2. Select `prateekm1007/MaestroAgent`
3. Set **Root Directory** to `download/MaestroAgent/maestro-personal`
4. Railway detects the `Dockerfile` automatically
5. Go to **Variables** tab and add:

```
MAESTRO_ENV=production
MAESTRO_PERSONAL_TOKEN=your-secret-token-here
PYTHONPATH=/app/src

# LLM (ZAI is free — copy from /etc/.z-ai-config on your machine):
# Option A: ZAI (free, rate-limited at 30 req/10min)
# Copy the entire contents of /etc/.z-ai-config into a file called
# .z-ai-config in the repo root, OR set these env vars:
# (ZAI reads from ~/.z-ai-config or /etc/.z-ai-config — on Railway,
#  create the file via a startup script or use OPENAI_API_KEY instead)

# Option B: OpenAI (recommended for production — no rate limit)
OPENAI_API_KEY=sk-your-openai-key

# OAuth connectors (optional — only if you want real Gmail/Slack/GitHub):
MAESTRO_GMAIL_CLIENT_ID=your-gmail-client-id
MAESTRO_GMAIL_CLIENT_SECRET=your-gmail-client-secret
MAESTRO_GMAIL_REDIRECT_URI=https://maestro-backend.up.railway.app/api/connectors/gmail/oauth/callback
MAESTRO_SLACK_CLIENT_ID=your-slack-client-id
MAESTRO_SLACK_CLIENT_SECRET=your-slack-client-secret
MAESTRO_SLACK_REDIRECT_URI=https://maestro-backend.up.railway.app/api/connectors/slack/oauth/callback
MAESTRO_GITHUB_CLIENT_ID=your-github-client-id
MAESTRO_GITHUB_CLIENT_SECRET=your-github-client-secret
MAESTRO_GITHUB_REDIRECT_URI=https://maestro-backend.up.railway.app/api/connectors/github/oauth/callback
```

6. Go to **Settings** → **Networking** → **Generate Domain**
7. You'll get: `https://maestro-backend.up.railway.app` (or similar)
8. Verify: `curl https://maestro-backend.up.railway.app/api/health` → `{"status":"ok"}`

## Step 2: Deploy the Web App

1. In the same Railway project → **New Service** → **GitHub repo** → same repo
2. Set **Root Directory** to `download/MaestroAgent/maestro-personal`
3. Railway detects `web/Dockerfile`
4. Go to **Variables** tab and add:

```
BACKEND_URL=https://maestro-backend.up.railway.app
PORT=3000
NODE_ENV=production
```

5. Go to **Settings** → **Networking** → **Generate Domain**
6. You'll get: `https://maestro-web.up.railway.app` (or similar)
7. Open it in your browser → login with your `MAESTRO_PERSONAL_TOKEN`

## Step 3: Seed Demo Data

From your local machine:

```bash
# Install the demo seeder's deps (if not already)
pip install requests

# Seed demo data into the Railway backend
MAESTRO_API_URL=https://maestro-backend.up.railway.app \
MAESTRO_DEMO_TOKEN=your-secret-token-here \
python3 scripts/seed_demo_data.py
```

## Step 4: Update Mobile App

In `mobile/src/api/client.ts`, the app already reads `EXPO_PUBLIC_API_URL`:

```bash
# For Expo dev (points at Railway instead of localhost):
export EXPO_PUBLIC_API_URL=https://maestro-backend.up.railway.app
npx expo start

# For EAS build (production):
eas build --profile production --platform ios
# (set EXPO_PUBLIC_API_URL in eas.json or EAS secrets)
```

## Step 5: Update OAuth Redirect URIs

If you set up OAuth connectors, update the redirect URIs in each provider's dashboard:

- **Google Cloud Console**: `https://maestro-backend.up.railway.app/api/connectors/gmail/oauth/callback`
- **Slack API**: `https://maestro-backend.up.railway.app/api/connectors/slack/oauth/callback`
- **GitHub OAuth App**: `https://maestro-backend.up.railway.app/api/connectors/github/oauth/callback`

## Cost Estimate (Railway trial)

| Service | Plan | Cost |
|---------|------|------|
| Backend (FastAPI) | Hobby ($5/mo) | $5/mo |
| Web (Next.js) | Hobby ($5/mo) | $5/mo |
| **Total** | | **$10/mo** |
| LLM (ZAI) | Free | $0 |
| LLM (OpenAI gpt-4o-mini) | Pay per use | ~$0.50/user/mo |

Your 30-day trial gives ~$5 in free credits — enough for the first month.

## Verification Checklist

- [ ] Backend health check returns 200: `curl https://maestro-backend.up.railway.app/api/health`
- [ ] Web app loads: `https://maestro-web.up.railway.app`
- [ ] Login works with `MAESTRO_PERSONAL_TOKEN`
- [ ] Dashboard shows The Moment card (after seeding demo data)
- [ ] Ask returns answers with provenance
- [ ] More tab shows connectors
- [ ] Mobile app connects when `EXPO_PUBLIC_API_URL` is set
