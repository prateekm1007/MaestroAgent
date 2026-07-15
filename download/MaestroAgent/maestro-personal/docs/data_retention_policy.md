# Data Retention Policy — Maestro Personal

**Effective date:** 2026-07-14
**Applies to:** Maestro Personal API (port 8766) + mobile/web apps

## Overview

Maestro Personal stores user data to provide commitment tracking, AI-powered
answers, and real-time meeting intelligence. This document describes what data
is stored, how long it's retained, and how users can delete it.

## Data stored

### 1. Signals (core data)
- **What:** Entity, text, signal type, timestamp, source, metadata
- **Where:** SQLite database (`personal.db`, `signals` table)
- **Retention:** Indefinite until user deletes account
- **Example:** `entity="Maria Garcia", text="I will send the proposal by Friday", signal_type="commitment_made"`

### 2. OAuth tokens (connectors)
- **What:** Encrypted access + refresh tokens for Gmail, Slack, GitHub, Calendar
- **Where:** SQLite database (`connectors` table, Fernet-encrypted)
- **Retention:** Until user disconnects the connector or deletes account
- **Encryption:** Fernet symmetric encryption (or dev-mode fallback)
- **Note:** Raw messages are NEVER stored — only extracted commitments

### 3. Drafts (follow-up emails/messages)
- **What:** Draft subject, body, recipient, commitment reference, evidence refs
- **Where:** SQLite database (`drafts` table)
- **Retention:** Until resolved (approved/denied/used) or account deletion
- **Status tracking:** pending → approved/denied/used_as_draft/send_failed

### 4. Audit log
- **What:** Action type, provider, detail, timestamp
- **Where:** SQLite database (`connector_audit` table)
- **Retention:** Until account deletion
- **Purpose:** Transparency — users can see every action Maestro took

### 5. Auth tokens
- **What:** Bearer tokens for API authentication
- **Where:** SQLite database (`auth_tokens` table)
- **Retention:** Until user logs out (revokes) or token expires
- **Mobile storage:** iOS Keychain / Android Keystore (SecureStore)

### 6. Calibration data (learning loop)
- **What:** Prediction registrations + outcomes (Complete/Dismiss)
- **Where:** SQLite database
- **Retention:** Until account deletion
- **Purpose:** Brier score calibration — improves prioritization over time

## Data NOT stored

- **Raw email bodies:** Gmail connector extracts commitments only, discards raw message text
- **Raw Slack messages:** Same — commitments extracted, raw text discarded
- **Raw audio:** Wit.ai/Whisper transcribes, audio file discarded after transcription
- **Raw calendar event details:** Only entity + summary + timestamp stored, not full event metadata
- **Passwords:** Only bearer tokens stored, never plaintext passwords

## User controls

### Export all data
- **Endpoint:** `GET /api/account/export`
- **Returns:** JSON with all signals, timestamps, entities
- **Mobile:** Settings → Export All Data (shares via OS share sheet)

### Delete all data
- **Endpoint:** `DELETE /api/account`
- **Behavior:** Deletes ALL user data from ALL tables (signals, tokens, drafts, audit log, calibration)
- **Mobile:** Settings → Delete Account (requires typing "DELETE" to confirm)
- **Irreversible:** No backup, no recovery

### Disconnect a connector
- **Endpoint:** `DELETE /api/connectors/{provider}`
- **Behavior:** Deletes the OAuth token for that provider only
- **Note:** Previously ingested signals remain (they're your data, not the connector's)

### Revoke consent
- **Mobile:** Copilot consent can be revoked at any time → recording stops immediately
- **Connectors:** Each connector can be disconnected independently

## Compliance

- **GDPR:** Right to access (export), right to erasure (delete), data portability (JSON export)
- **CCPA:** Right to know (export), right to delete, right to opt-out (disconnect connectors)
- **Data minimization:** Only commitments extracted — raw messages never stored
- **Encryption at rest:** OAuth tokens encrypted with Fernet; auth tokens hashed

## Verification

This policy matches the actual code behavior. To verify:

```bash
# Export all data
curl -H "Authorization: Bearer $TOKEN" http://localhost:8766/api/account/export

# Delete all data
curl -X DELETE -H "Authorization: Bearer $TOKEN" http://localhost:8766/api/account

# Verify data is gone
curl -H "Authorization: Bearer $TOKEN" http://localhost:8766/api/signals
# Expected: 401 (token revoked) or empty list
```

## Changes to this policy

If retention practices change, this document will be updated and the version
date will change. Users will be notified in-app before any policy change that
affects their data.
