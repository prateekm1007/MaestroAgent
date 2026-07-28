# Email Composition Feature - Deployment Checklist

## Overview
This checklist covers the deployment of the email composition and voice matching feature.

## Pre-Deployment Requirements

### 1. Environment Variables (Railway)
**Backend service must have:**
- OPENROUTER_API_KEY (for LLM draft generation)
- GMAIL_CLIENT_ID (from Google Cloud Console)
- GMAIL_CLIENT_SECRET (from Google Cloud Console)
- GMAIL_REDIRECT_URI=https://maestroagent-production.up.railway.app/api/auth/gmail/callback
- DATABASE_URL (postgres connection string)
- APP_ENV=production

### 2. Gmail OAuth Setup
- Google Cloud Console project exists
- Gmail API is enabled
- OAuth 2.0 credentials created (Web application type)
- Authorized redirect URIs include the callback URL
- OAuth consent screen configured with gmail.modify scope

## Deployment Steps

### Phase 1: Backend Deployment
1. Verify commits are on main (email_models.py, routers/email.py, voice_analyzer.py, draft_generator.py, email_sender.py)
2. Check Railway auto-deploy completed successfully
3. Test backend endpoints manually with curl
4. Verify Gmail OAuth flow works

### Phase 2: Frontend Deployment
1. Verify page.tsx modification is on main
2. Check Railway auto-deploy completed successfully
3. Test frontend integration (click commitment cards, verify modal opens)
4. Test each tab (Thread, Draft, Voice)

### Phase 3: End-to-End Testing
1. Create/connect test account with Gmail
2. Test commitment click flow
3. Test thread viewing
4. Test draft generation
5. Test draft editing
6. Test email sending
7. Test voice profile display

## Rollback Procedures
- Backend: `git revert HEAD~5..HEAD`
- Frontend: `git revert HEAD`
- Disable feature: Remove ClickableCard wrapper from page.tsx

## Success Criteria
- All backend endpoints return 200
- Frontend builds without errors
- Commitment cards are clickable
- Modal opens with three tabs
- Thread/Draft/Voice tabs work correctly
- No console errors
- No 500 errors in logs
