# Slack + GitHub OAuth Setup Guide

## Why You Need This

The Slack and GitHub connectors are **real** — they call the actual Slack Web API and GitHub REST API. But they need OAuth credentials (client ID + secret) to work. Without them, clicking "Connect Slack" or "Connect GitHub" stores a fake demo token, and sync returns **empty** (no fabricated data).

This guide walks you through creating Slack + GitHub OAuth apps and configuring the env vars so the connectors work for real.

---

## 1. Slack OAuth App Setup

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. App name: `MaestroAgent`
4. Pick your Slack workspace
5. Click **"Create App"**

### Step 2: Configure OAuth Scopes

Go to **OAuth & Permissions** → **Scopes** → **Bot Token Scopes** and add:
```
channels:read
groups:read
im:read
im:history
chat:write
users:read
```

### Step 3: Set Redirect URL

Go to **OAuth & Permissions** → **Redirect URLs** and add:
```
http://localhost:8766/api/connectors/slack/oauth/callback
```
(For production: `https://your-domain.com/api/connectors/slack/oauth/callback`)

### Step 4: Get Your Credentials

Go to **Basic Information** → **App Credentials**:
- Copy the **Client ID** → `MAESTRO_SLACK_CLIENT_ID`
- Copy the **Client Secret** → `MAESTRO_SLACK_CLIENT_SECRET`

### Step 5: Install the App

Go to **OAuth & Permissions** → click **"Install to Workspace"** → authorize.

### Step 6: Set Env Vars

```cmd
set MAESTRO_SLACK_CLIENT_ID=your_client_id_here
set MAESTRO_SLACK_CLIENT_SECRET=your_client_secret_here
set MAESTRO_SLACK_REDIRECT_URI=http://localhost:8766/api/connectors/slack/oauth/callback
```

---

## 2. GitHub OAuth App Setup

### Step 1: Create a GitHub OAuth App

1. Go to https://github.com/settings/developers
2. Click **"New OAuth App"**
3. Application name: `MaestroAgent`
4. Homepage URL: `http://localhost:3000`
5. Authorization callback URL: `http://localhost:8766/api/connectors/github/oauth/callback`
6. Click **"Register application"**

### Step 2: Get Your Credentials

On the app settings page:
- Copy the **Client ID** → `MAESTRO_GITHUB_CLIENT_ID`
- Click **"Generate a new client secret"** → copy it → `MAESTRO_GITHUB_CLIENT_SECRET`

### Step 3: Set Env Vars

```cmd
set MAESTRO_GITHUB_CLIENT_ID=your_client_id_here
set MAESTRO_GITHUB_CLIENT_SECRET=your_client_secret_here
set MAESTRO_GITHUB_REDIRECT_URI=http://localhost:8766/api/connectors/github/oauth/callback
```

---

## 3. Start the Backend with All Env Vars

Create a batch file `start_backend.bat`:

```cmd
@echo off
cd C:\Users\Administrator\MaestroAgent\download\MaestroAgent\maestro-personal
set PYTHONPATH=src
set MAESTRO_DEMO_MODE=0

REM Gmail (if you have it)
set MAESTRO_GMAIL_CLIENT_ID=your_gmail_client_id
set MAESTRO_GMAIL_CLIENT_SECRET=your_gmail_client_secret

REM Slack
set MAESTRO_SLACK_CLIENT_ID=your_slack_client_id
set MAESTRO_SLACK_CLIENT_SECRET=your_slack_client_secret

REM GitHub
set MAESTRO_GITHUB_CLIENT_ID=your_github_client_id
set MAESTRO_GITHUB_CLIENT_SECRET=your_github_client_secret

python -m maestro_personal_shell.api
```

**Important:** Set `MAESTRO_DEMO_MODE=0` (or remove it) so the app doesn't store fake demo tokens.

---

## 4. Test the Real Connectors

1. Start the backend: `start_backend.bat`
2. Start the web app: `cd web && npm run dev`
3. Open http://localhost:3000
4. Go to **Settings** → **Connectors**
5. Click **"Connect Slack"** → you'll be redirected to Slack's consent screen
6. Authorize → redirected back → "Slack Connected!"
7. Click **"Sync"** → real DMs are ingested as signals
8. Repeat for **GitHub** → real assigned issues are ingested

---

## What Changed (for developers)

### Before (fabricated):
- Click "Connect Slack" with no OAuth env vars → stored `"demo-token-not-real"`
- Click "Sync" → returned `MOCK_INGESTION_DATA` (4 fake signals with "Maria Garcia", "Sam Patel", etc.)
- The user thought real Slack data was ingested — it wasn't

### After (honest):
- Click "Connect Slack" with no OAuth env vars → stores demo token (only if `MAESTRO_DEMO_MODE=1`)
- Click "Sync" → returns **empty list** (no fabrication)
- The UI shows "No signals yet" — honest empty state
- With real OAuth env vars: clicking "Connect Slack" starts the real OAuth flow → real token stored → real DMs ingested

### Code changes:
- `connectors.py::_fetch_messages()` — Slack + GitHub paths now return `[]` instead of `MOCK_INGESTION_DATA` when OAuth isn't configured or the token is a demo token
- Tests updated: `test_returns_empty_when_oauth_not_configured` replaces `test_falls_back_to_mock_when_oauth_not_configured`
