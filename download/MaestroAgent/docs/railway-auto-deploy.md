# Railway Auto-Deploy Configuration

## Principle P71: If it runs in production, it auto-deploys from main. No manual deploys.

## Current State

| Service | URL | Auto Deploy | Branch | Health Check | Status |
|---------|-----|-------------|--------|--------------|--------|
| Backend | maestroagent-production.up.railway.app | ✅ Enabled | main | /api/health | Working |
| Web | web-production-d5c26.up.railway.app | ❌ **NOT CONFIGURED** | main | / | **STALE** |

## The Problem

The web frontend service on Railway is NOT configured for auto-deploy. This means:

1. Code fixes merged to main reach the backend within ~90 seconds ✅
2. Code fixes merged to main do NOT reach the web frontend ❌
3. The web service continues serving old code until someone manually triggers a deploy

This violates P71 (infrastructure automation) and FA28 (no manual production deploys).

## Manual Steps to Fix (REQUIRED — Railway API token expired)

The Railway API token (`e3d39b32-d40a-4405-9c08-958acaae92c8`) has expired (403 Forbidden). Auto-deploy cannot be configured programmatically. The following manual steps are required:

### Step 1: Go to Railway Dashboard

1. Navigate to https://railway.app
2. Log in
3. Select the project ("brilliant-vision" or similar)

### Step 2: Find the Web Service

1. Click on the web service (the one serving `web-production-d5c26.up.railway.app`)
2. Go to **Settings** → **Deploy**

### Step 3: Enable Auto-Deploy

1. Toggle **"Auto Deploy"** ON
2. Set **"Branch"** to `main`
3. Set **"Root Directory"** to `download/MaestroAgent/maestro-personal/web` (the web app directory in the monorepo)
4. Set **"Health Check Path"** to `/`
5. Save changes

### Step 4: Trigger Immediate Rebuild

1. Click **"Deploy"** → **"Deploy Latest Commit"**
2. Wait for the build to complete (2-5 minutes)
3. Verify: `curl -s https://web-production-d5c26.up.railway.app/ | grep -o "Q3 budget"` should return NOTHING (mock data gone)

### Step 5: Verify Auto-Deploy Works

After enabling, push a test commit:

```bash
git commit --allow-empty -m "test: verify web auto-deploy"
git push origin main
sleep 300  # Wait 5 minutes
curl -s https://web-production-d5c26.up.railway.app/ | grep -c "Q3 budget"
# Should return 0 (no mock data)
```

## How to Verify Auto-Deploy After Any PR Merge

```bash
# Get the latest commit hash
LATEST_COMMIT=$(git rev-parse HEAD)

# Wait 3-5 minutes
sleep 300

# Check backend
BACKEND_COMMIT=$(curl -s https://maestroagent-production.up.railway.app/api/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('commit',''))")
if [ "$BACKEND_COMMIT" = "$LATEST_COMMIT" ]; then
  echo "✅ Backend auto-deployed: $BACKEND_COMMIT"
else
  echo "❌ Backend not deployed: expected $LATEST_COMMIT, got $BACKEND_COMMIT"
fi

# Check web (look for absence of mock data)
WEB_HTML=$(curl -s https://web-production-d5c26.up.railway.app/)
if echo "$WEB_HTML" | grep -q "Q3 budget proposal"; then
  echo "❌ Web still showing mock data — deploy failed or not triggered"
else
  echo "✅ Web deployed — no mock data found"
fi
```

## Troubleshooting

### Deploy not triggering

1. Check Railway dashboard: Settings → Deploy → "Auto Deploy" toggle
2. Check deploy logs: Railway dashboard → Deployments → latest deploy → View Logs
3. Check GitHub webhook: Railway dashboard → Settings → GitHub → Webhook status

### Deploy failing

1. Check deploy logs for errors
2. Common issues:
   - Missing environment variables (BACKEND_URL must be set)
   - Build script errors (check `npm run build` output)
   - Port not configured (Railway expects `PORT` env var)
   - Root directory incorrect (must be `download/MaestroAgent/maestro-personal/web`)

### Railway API token expired

The current token (`e3d39b32-...`) returns 403 Forbidden. To refresh:

1. Go to https://railway.app → Account Settings → API Tokens
2. Create a new token
3. Update `.env.local` with the new token
4. Update the GitHub remote if needed

## Forbidden Actions

- **FA28**: Manually deploying to production from the Railway dashboard (except emergency hotfixes)
- **P71**: Any production service without auto-deploy enabled

## Follow-up Ticket

File: "TICKET-22: Configure Railway auto-deploy via API or CLI"
- Railway API token expired — cannot configure programmatically
- Manual dashboard steps documented above
- Investigate Terraform/Pulumi for infrastructure-as-code
- Refresh Railway API token for automated verification
