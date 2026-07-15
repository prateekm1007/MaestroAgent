# Maestro Personal — Dogfood Install Guide

**Audience:** the first 5 dogfood users. This guide gets you from zero to a running Maestro Personal API in under 30 minutes.

## What you need

- A laptop with Python 3.12+ (Mac, Windows, or Linux)
- Git
- The Kaggle notebook URL (provided separately — hosts the LLM)
- Your `MAESTRO_PERSONAL_TOKEN` (provided separately — your local password)

## Step 1: Install Python 3.12

### Mac (with Homebrew)
```bash
brew install python@3.12
python3.12 --version  # should print Python 3.12.x
```

### Windows (PowerShell as Administrator)
```powershell
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe" -OutFile "python-installer.exe"
.\python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
```
Close and reopen PowerShell, then verify:
```powershell
python --version
```

### Linux (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install -y python3.12 python3.12-venv python3-pip
python3.12 --version
```

## Step 2: Clone the repo

```bash
git clone https://github.com/prateekm1007/MaestroAgent.git
cd MaestroAgent/download/MaestroAgent/maestro-personal
```

## Step 3: Install dependencies

```bash
pip install fastapi uvicorn httpx pydantic pytest pytest-asyncio
pip install -e ../backend/
```

If you get a permissions error, add `--user`:
```bash
pip install --user fastapi uvicorn httpx pydantic
```

## Step 4: Set environment variables

You need three env vars. Replace the values with what was provided to you:

### Mac/Linux
```bash
export MAESTRO_PERSONAL_TOKEN="your-token-here"
export OLLAMA_HOST="https://provided-around-suffering-mas.trycloudflare.com"
export OLLAMA_MODEL="llama3:8b"
export PYTHONPATH=src
```

### Windows (PowerShell)
```powershell
$env:MAESTRO_PERSONAL_TOKEN = "your-token-here"
$env:OLLAMA_HOST = "https://provided-around-suffering-mas.trycloudflare.com"
$env:OLLAMA_MODEL = "llama3:8b"
$env:PYTHONPATH = "src"
```

**Important:** The `OLLAMA_HOST` URL points at a shared GPU running on Kaggle. It's alive for 12 hours at a time. If it's down, ask for a new URL — the notebook needs to be re-run.

## Step 5: Start the API

```bash
python -m maestro_personal_shell.api
```

You should see:
```
  Maestro Personal API
  Port: 8766
  Health: http://localhost:8766/api/health
```

**Leave this terminal open.** The API is now running on your laptop.

## Step 6: Verify it works

Open a **new terminal** and run:

```bash
curl http://localhost:8766/api/health
```

Should return:
```json
{"status":"ok","service":"maestro-personal","version":"1.0.0"}
```

Now test login + LLM status:

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:8766/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"your-token-here"}' | python -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "Your bearer token: $TOKEN"

# Check LLM status
curl -s http://localhost:8766/api/llm-status -H "Authorization: Bearer $TOKEN"
```

You should see `"verified": true` and `"provider": "ollama"` in the response. If `verified` is `false`, the Kaggle tunnel is down — ask for a new URL.

## Step 7: Seed your first signal

```bash
curl -s -X POST http://localhost:8766/api/signals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity":"Alex Chen","text":"I will send Alex the pricing deck by Friday","signal_type":"commitment_made"}'
```

## Step 8: Ask a question

```bash
curl -s -X POST http://localhost:8766/api/ask \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query":"What did I promise Alex?"}'
```

The answer should mention Alex and the pricing deck. This takes ~20-30 seconds because it calls the LLM on the Kaggle GPU.

## 14-Day Dogfood Protocol

### Days 1-2: Seed your history
- Add 20+ signals from your real work history (emails, meeting notes, commitments you've made)
- Use `signal_type: "commitment_made"` for promises, `"reported_statement"` for observations
- Backdate with `"timestamp": "2026-04-15T10:00:00Z"` for historical imports

### Days 3-7: Use it daily
- Morning: check `/api/briefing` and `/api/the-moment`
- Before each meeting: check `/api/prepare`
- When you make a commitment: immediately POST it as a signal
- When you complete/break one: POST a completion/break signal
- Ask 3-5 questions per day via `/api/ask`

### Day 7: First survey
Your dogfood coordinator will send you a 5-question survey:
1. Did Maestro catch something you would have missed?
2. Did Maestro miss something obvious?
3. Was the LLM latency acceptable?
4. Did any false positives annoy you?
5. Would you continue using it?

### Days 8-13: Deepen usage
- Add Slack/email transcripts via `/api/ingest/slack` and `/api/ingest/transcript`
- Try the Whisper surface daily: `/api/whisper`
- Dismiss irrelevant whispers via `/api/signals/{id}/correct?action=dismiss` (this trains the learning loop)

### Day 14: Final survey
The north-star question:
> **If Maestro disappeared tomorrow, would you feel you lost a meaningful intelligence layer?**

## Troubleshooting

### "Connection refused" on localhost:8766
The API isn't running. Go back to Step 5.

### LLM status shows `verified: false`
The Kaggle tunnel is down. Ask for a new URL and update `OLLAMA_HOST`.

### Ask takes >60 seconds
The LLM is slow or the tunnel is congested. Retry. If it persists, the tunnel may be dying.

### "401 Unauthorized" on authenticated endpoints
Your bearer token expired (30-day TTL) or you didn't login. Re-run the login curl from Step 6.

### Python import errors
Make sure `PYTHONPATH=src` is set in the terminal where you start the API.

## Getting help

- **API docs:** `http://localhost:8766/docs` (interactive Swagger UI)
- **Health check:** `http://localhost:8766/api/health`
- **LLM status:** `http://localhost:8766/api/llm-status` (requires auth)
- **Report bugs:** post in the dogfood channel with the trace_id from the response

## What Maestro does NOT do (yet)

- No OAuth to Gmail/Calendar (manual signal entry only for now)
- No push notifications (check the API manually)
- No multi-user (your data is isolated to your token, but there's no real IdP)
- No mobile app (use curl or the Swagger UI)

This is a controlled beta. The goal is to prove the intelligence layer is worth building the rest around.
