@echo off
REM ============================================================
REM  MaestroAgent Backend Start Script
REM  Edit the credentials below with your real OAuth app credentials.
REM  See docs/CONNECTOR_OAUTH_SETUP.md for setup instructions.
REM ============================================================

cd /d C:\Users\Administrator\MaestroAgent\download\MaestroAgent\maestro-personal

set PYTHONPATH=src
set MAESTRO_DEMO_MODE=0

REM --- Google (Gmail + Calendar share ONE OAuth app) ---
REM Create at: https://console.cloud.google.com/ → APIs & Services → Credentials
set MAESTRO_GMAIL_CLIENT_ID=your_google_client_id
set MAESTRO_GMAIL_CLIENT_SECRET=your_google_client_secret
set MAESTRO_GMAIL_REDIRECT_URI=http://localhost:8766/api/connectors/gmail/oauth/callback

set MAESTRO_CALENDAR_CLIENT_ID=your_google_client_id
set MAESTRO_CALENDAR_CLIENT_SECRET=your_google_client_secret
set MAESTRO_CALENDAR_REDIRECT_URI=http://localhost:8766/api/connectors/calendar/oauth/callback

REM --- Slack ---
REM Create at: https://api.slack.com/apps
set MAESTRO_SLACK_CLIENT_ID=your_slack_client_id
set MAESTRO_SLACK_CLIENT_SECRET=your_slack_client_secret
set MAESTRO_SLACK_REDIRECT_URI=http://localhost:8766/api/connectors/slack/oauth/callback

REM --- GitHub ---
REM Create at: https://github.com/settings/developers
set MAESTRO_GITHUB_CLIENT_ID=your_github_client_id
set MAESTRO_GITHUB_CLIENT_SECRET=your_github_client_secret
set MAESTRO_GITHUB_REDIRECT_URI=http://localhost:8766/api/connectors/github/oauth/callback

echo Starting MaestroAgent backend on http://localhost:8766
echo.
echo Connectors configured:
echo   Gmail:    %MAESTRO_GMAIL_CLIENT_ID:~0,10%...
echo   Calendar: %MAESTRO_CALENDAR_CLIENT_ID:~0,10%...
echo   Slack:    %MAESTRO_SLACK_CLIENT_ID:~0,10%...
echo   GitHub:   %MAESTRO_GITHUB_CLIENT_ID:~0,10%...
echo.

python -m maestro_personal_shell.api
