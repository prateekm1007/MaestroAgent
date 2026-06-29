# Historical Import Engine

Real-time, parallel ingestion of organizational history from GitHub, Jira, Slack,
Confluence, and Gmail into the Maestro OEM (Organizational Execution Memory).

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Frontend (app.html)                         │
│  Settings → Connect GitHub button → /api/oauth/github/start     │
│  Import banner ← WebSocket /api/imports/{id}/stream             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     maestro_api (FastAPI)                        │
│  /api/oauth/*         /api/imports/*                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│             maestro_oem (the import pipeline)                    │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │             HistoricalImportEngine                       │    │
│  │  (parallel asyncio.gather across 5 providers)            │    │
│  └──┬──────────────────────────────────────────────────┬────┘    │
│     │                                                  │         │
│  ┌──▼─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────▼───┐    │
│  │ GitHub     │  │ Jira     │  │ Slack    │  │ Confluence  │    │
│  │ Fetcher    │  │ Fetcher  │  │ Fetcher  │  │ /Gmail      │    │
│  └──┬─────────┘  └──┬───────┘  └──┬───────┘  └──┬──────────┘    │
│     │               │             │              │              │
│  ┌──▼───────────────▼─────────────▼──────────────▼──────────┐   │
│  │              ProgressTracker (live updates)                │   │
│  └────────────────────────┬──────────────────────────────────┘   │
│  ┌────────────────────────▼──────────────────────────────────┐   │
│  │               CheckpointStore (SQLite)                     │   │
│  │  jobs · checkpoints · oauth_credentials · connections     │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │            OEM Engine (live_ingest)                        │   │
│  │  Each page of signals → engine.ingest() → dashboard       │   │
│  │  improves in real time (patterns, laws, recommendations)  │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## What it does

1. **User connects a provider** (e.g., GitHub) via the Settings page.
2. The OAuth flow exchanges an authorization code for access/refresh tokens.
3. On successful connection, a **background historical import** starts automatically:
   - 5 years of history (configurable via `since` parameter)
   - All available data: PRs, issues, commits, reviews, messages, pages, emails
4. The OEM engine updates **continuously** — every page of signals triggers
   `engine.ingest()` so the dashboard shows new patterns, laws, and recommendations
   in real time.
5. Progress is streamed to the UI via WebSocket with:
   - Events processed count
   - ETA based on throughput
   - Live OEM snapshot (patterns discovered, laws emerging, recommendations improving)
6. Checkpoints are persisted to SQLite every page, so:
   - Server restart → job resumes from last checkpoint
   - User cancels → job can be resumed later
   - OAuth token expires → refresh + retry (no data loss)
7. Rate limits are honored per-provider (GitHub 5000/hr, Slack 20/min, etc.)
   with `Retry-After` header parsing.

## Components

### `CheckpointStore` (`maestro_oem/checkpoint_store.py`)
SQLite-backed persistence for jobs, checkpoints, OAuth credentials, and
provider connections. Thread-safe via a re-entrant lock.

### `OAuthManager` (`maestro_oem/oauth_manager.py`)
Real OAuth 2.0 flows for all 5 providers:
- GitHub (authorization code → access token)
- Jira / Confluence (Atlassian Cloud 3LO)
- Slack (OAuth v2)
- Gmail (Google OAuth 2.0)

Each flow includes:
- CSRF protection via signed `state` parameter
- Token refresh on expiry
- Token revocation on disconnect
- Credential persistence via `CheckpointStore`

### `ConnectionManager` (`maestro_oem/connection_manager.py`)
Tracks which providers are connected. On connect, triggers a historical
import via `HistoricalImportEngine`. On disconnect, cancels in-flight
imports for that provider.

### `ProgressTracker` (`maestro_oem/progress_tracker.py`)
In-memory live progress for all running jobs. Subscribers (WebSocket
clients) receive JSON snapshots at ~4 Hz.

### `ProviderFactory` (`maestro_oem/importers/factory.py`)
Single dispatch point — given a provider name, returns the right
`PageFetcher` instance.

### `HistoricalImportEngine` (`maestro_oem/historical_engine.py`)
The orchestrator. Runs all providers in parallel via `asyncio.gather`.
For each provider:
1. Creates a fetcher
2. Resumes from `CheckpointStore` if there's an incomplete checkpoint
3. Streams pages through the existing `IngestionPipeline` normalizers
4. Calls `oem_state.live_ingest(new_signals)` after each page → dashboard
   improves continuously
5. Updates `ProgressTracker` after each page
6. Persists checkpoint after each page

## API Endpoints

### OAuth
- `GET /api/oauth/status` — connection status for all 5 providers
- `GET /api/oauth/{provider}/start` — returns authorization URL
- `GET /api/oauth/callback?code=...&state=...&provider=...` — OAuth redirect target
- `POST /api/oauth/{provider}/disconnect` — revoke tokens

### Imports
- `GET /api/imports` — list all import jobs
- `POST /api/imports/start` — start a new import (body: `{providers, since}`)
- `GET /api/imports/{job_id}` — get job progress
- `POST /api/imports/{job_id}/cancel` — cancel a running job
- `GET /api/imports/{job_id}/checkpoints` — list per-provider checkpoints
- `WS /api/imports/{job_id}/stream` — live progress stream (~4 Hz)

### OEM
- `GET /api/oem/snapshot` — current OEM state counts (signals, patterns, laws, recs)

## Configuration

### Environment variables

```bash
# OAuth client IDs and secrets (one per provider)
MAESTRO_OAUTH_GITHUB_CLIENT_ID=Iv1.abc123
MAESTRO_OAUTH_GITHUB_CLIENT_SECRET=...
MAESTRO_OAUTH_JIRA_CLIENT_ID=...
MAESTRO_OAUTH_JIRA_CLIENT_SECRET=...
MAESTRO_OAUTH_SLACK_CLIENT_ID=...
MAESTRO_OAUTH_SLACK_CLIENT_SECRET=...
MAESTRO_OAUTH_CONFLUENCE_CLIENT_ID=...
MAESTRO_OAUTH_CONFLUENCE_CLIENT_SECRET=...
MAESTRO_OAUTH_GMAIL_CLIENT_ID=...
MAESTRO_OAUTH_GMAIL_CLIENT_SECRET=...

# OAuth redirect URI (shared)
MAESTRO_OAUTH_REDIRECT_URI=http://localhost:8765/api/oauth/callback

# Import state DB (defaults to backend/import_state.db)
MAESTRO_IMPORT_DB=/var/lib/maestro/import_state.db
```

### OAuth App Registration

| Provider  | Where to register | Required scopes |
|-----------|-------------------|-----------------|
| GitHub    | https://github.com/settings/developers | `repo`, `read:org`, `read:user` |
| Jira      | https://developer.atlassian.com/console/myapps/ | `read:jira-work`, `read:jira-user`, `offline_access` |
| Slack     | https://api.slack.com/apps | `channels:history`, `channels:read`, `groups:history`, `groups:read`, `im:history`, `im:read`, `mpim:history`, `mpim:read`, `users:read`, `team:read` |
| Confluence| https://developer.atlassian.com/console/myapps/ | `read:confluence-content.all`, `read:confluence-space.summary`, `offline_access` |
| Gmail     | https://console.cloud.google.com/apis/credentials | `gmail.readonly`, `gmail.metadata` |

## Testing

All new code is tested. Run the full suite:

```bash
cd backend
python -m pytest maestro_oem/tests/ maestro_api/tests/ -v
```

Test coverage:
- `test_checkpoint_store.py` — SQLite persistence (CRUD, upsert, resume)
- `test_oauth_manager.py` — OAuth flow (auth URL, code exchange, refresh, revoke, state token)
- `test_progress_tracker.py` — Live progress tracking and subscriber callbacks
- `test_github_importer.py` — GitHub fetcher (pagination, rate limits, auth refresh, normalization)
- `test_providers.py` — Jira/Slack/Confluence/Gmail fetchers + ProviderFactory
- `test_historical_engine.py` — End-to-end engine (parallel, resume, restart, OAuth expiry, rate limits, large history)
- `test_imports_routes.py` — API route integration

## Verification

To verify with a real GitHub repo:

1. Set up env vars:
   ```bash
   export MAESTRO_OAUTH_GITHUB_CLIENT_ID=Iv1.your_app_id
   export MAESTRO_OAUTH_GITHUB_CLIENT_SECRET=your_secret
   export MAESTRO_OAUTH_REDIRECT_URI=http://localhost:8765/api/oauth/callback
   ```

2. Start the server:
   ```bash
   cd backend
   python -m maestro_cli.main serve --port 8765
   ```

3. Open http://localhost:8765 in a browser.

4. Navigate to **Engineering → Settings → Signal Sources**.

5. Click **Connect** on GitHub.

6. Authorize on github.com.

7. After the redirect, watch the import banner at the bottom of the screen:
   ```
   Importing GitHub…
   142,315 events processed · ETA 3m
   Patterns: 12   Laws: 3   Recs: 5
   ```

8. Verify on the Home dashboard that:
   - Receipts (recent discoveries) grow in real time
   - Patterns (Hayek Lens) emerge as the import progresses
   - Laws (Physics) appear with evidence chains
   - Recommendations (Inbox) update
   - Ask the Org autocomplete surfaces real entities

## Restart / Resume

If the server restarts mid-import:
- The lifespan hook calls `engine.resume_incomplete_jobs()`
- All jobs with `status = 'running'` and incomplete checkpoints are resumed
- Each provider picks up from its last saved checkpoint
- No data is lost; no work is duplicated
