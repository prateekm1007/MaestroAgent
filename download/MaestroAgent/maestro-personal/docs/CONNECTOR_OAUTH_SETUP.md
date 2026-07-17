# Connector OAuth Setup Guide

## Why You Need This

All 4 connectors (Gmail, Calendar, Slack, GitHub) make **real API calls** to real provider APIs. They need OAuth credentials (client ID + secret) to work. Without them, clicking "Connect" returns a 400 error with instructions on what to set.

There is **no demo mode** — the connectors are 100% real or they fail closed.

---

## 1. Google OAuth App (Gmail + Calendar share ONE app)

Gmail and Calendar both use Google OAuth2, so you create ONE Google OAuth app and reuse the credentials for both.

### Step 1: Create a Google OAuth App

1. Go to https://console.cloud.google.com/
2. Create or select a project
3. Go to **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
4. Application type: **Web application**
5. Name: `MaestroAgent`
6. Authorized redirect URIs — add BOTH:
   ```
   http://localhost:8766/api/connectors/gmail/oauth/callback
   http://localhost:8766/api/connectors/calendar/oauth/callback
   ```
7. Click **Create**

### Step 2: Enable APIs

1. Go to **APIs & Services** → **Library**
2. Search for **Gmail API** → click **Enable**
3. Search for **Google Calendar API** → click **Enable**

### Step 3: Get Your Credentials

On the Credentials page:
- Copy the **Client ID** → this is your `MAESTRO_GMAIL_CLIENT_ID` AND `MAESTRO_CALENDAR_CLIENT_ID`
- Copy the **Client Secret** → this is your `MAESTRO_GMAIL_CLIENT_SECRET` AND `MAESTRO_CALENDAR_CLIENT_SECRET`

### Step 4: Set Env Vars

Gmail and Calendar share the same client ID/secret:
```cmd
set MAESTRO_GMAIL_CLIENT_ID=your_google_client_id
set MAESTRO_GMAIL_CLIENT_SECRET=your_google_client_secret
set MAESTRO_GMAIL_REDIRECT_URI=http://localhost:8766/api/connectors/gmail/oauth/callback

set MAESTRO_CALENDAR_CLIENT_ID=your_google_client_id
set MAESTRO_CALENDAR_CLIENT_SECRET=your_google_client_secret
set MAESTRO_CALENDAR_REDIRECT_URI=http://localhost:8766/api/connectors/calendar/oauth/callback
```

---

## 2. Slack OAuth App

### Step 1: Create a Slack App

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From scratch"**
3. App name: `MaestroAgent`
4. Pick your Slack workspace
5. Click **"Create App"**

### Step 2: Configure OAuth Scopes

Go to **OAuth & Permissions** → **Bot Token Scopes** and add:
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

### Step 4: Get Your Credentials

Go to **Basic Information** → **App Credentials**:
- Copy the **Client ID** → `MAESTRO_SLACK_CLIENT_ID`
- Copy the **Client Secret** → `MAESTRO_SLACK_CLIENT_SECRET`

### Step 5: Install the App

Go to **OAuth & Permissions** → click **"Install to Workspace"** → authorize.

### Step 6: Set Env Vars

```cmd
set MAESTRO_SLACK_CLIENT_ID=your_slack_client_id
set MAESTRO_SLACK_CLIENT_SECRET=your_slack_client_secret
set MAESTRO_SLACK_REDIRECT_URI=http://localhost:8766/api/connectors/slack/oauth/callback
```

---

## 3. GitHub OAuth App

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
set MAESTRO_GITHUB_CLIENT_ID=your_github_client_id
set MAESTRO_GITHUB_CLIENT_SECRET=your_github_client_secret
set MAESTRO_GITHUB_REDIRECT_URI=http://localhost:8766/api/connectors/github/oauth/callback
```

---

## 4. Start the Backend with All Env Vars

Use the included `start_backend.bat` (in the `maestro-personal/` directory). Edit it with your actual credentials, then run it.

**Important:** Do NOT set `MAESTRO_DEMO_MODE=1` — there is no demo mode anymore. The connectors are real or they fail closed.

---

## 5. Test the Real Connectors

1. Start the backend: `start_backend.bat`
2. Start the web app: `cd web && npm run dev`
3. Open http://localhost:3000
4. Go to **More** tab → **Connectors** section
5. Click **"Connect Gmail"** → you'll be redirected to Google's consent screen
6. Authorize → redirected back → "Gmail Connected!"
7. Click **"Sync"** → real Gmail messages are ingested as signals
8. Repeat for Calendar, Slack, GitHub

## What happens without OAuth configured?

Clicking "Connect" returns a 400 error:
```
Gmail OAuth not configured. Set MAESTRO_GMAIL_CLIENT_ID and
MAESTRO_GMAIL_CLIENT_SECRET environment variables to enable real OAuth.
See docs/CONNECTOR_OAUTH_SETUP.md for setup instructions.
```

No fake "Connected" status. No demo tokens. No fabricated data. Honest failure.
