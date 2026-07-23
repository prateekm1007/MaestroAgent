# OPS-002-work-email-ui-fix — Work email UI fix — 401→400 (stop session-clearing), IMAP auto-detect, Playwright E2E

- **Created:** 2026-07-23T18:14:55.164709+00:00 | **Source:** user_report (Prateek)
- **Agents:** Diagnostician, Repair, Verifier
- **Outcome:** RESOLVED

## Detect
Prateek tried the Work Email connector and it did not work. The backend was verified (fake creds → honest 401, connector listed), but the actual button-to-result flow was not verified in a real browser. Third UI-layer failure in this arc (SSR Loading…, connector listed but not usable, work email button).

## Diagnose
ROOT CAUSE: The backend returned HTTP 401 for IMAP connection failures. maestroFetch treats 401 as "auth expired" → clears the user session token → shows Session Expired dialog → page reloads. So when Prateek entered his work email credentials and the IMAP connection failed (wrong password / 2FA), the app LOGGED HIM OUT instead of showing the honest error.

Secondary issue: maestroFetch threw "HTTP 400" with no detail — the response body (containing the honest error message) was discarded.

Tertiary issue: users do not know their IMAP host. Requiring manual entry of imap.gmail.com / outlook.office365.com / port 993 is a friction point that fails for nearly every non-technical user.

## Govern
- Change IMAP failure status from 401 to 400: ALLOW (Level 2, code change)
- Include response body detail in maestroFetch error: ALLOW (Level 2, code change)
- Add IMAP host auto-detection from email domain: ALLOW (Level 2, UX improvement)
- Add app-password/2FA guidance to form: ALLOW (Level 2, UX improvement)

## Execute
- Backend: IMAP failures now return 400 (not 401). Error messages now guide: "Check your app password — if 2FA is enabled, generate an app password in your provider security settings. Also confirm IMAP is enabled."
- Frontend: maestroFetch now includes response body detail in error. Previously threw "HTTP 400" with no detail; now throws the actual error message so the toast shows the honest, guiding error.
- UX: IMAP host auto-detection from email domain. Typing you@gmail.com auto-fills host=imap.gmail.com:993. Supports Gmail, Outlook/Hotmail/Live/Office365, Yahoo, iCloud/Me/Mac, Zoho, ProtonMail Bridge, Fastmail. Work Email field is now primary (full-width), host/port below (labeled auto-filled). App Password field has guidance.
- Playwright E2E test (e2e_work_email.py): verifies the full button-to-result flow in a real browser — Connect button → form opens → email auto-detects host → Connect & Verify fires API → honest error displayed → user stays logged in.

## Verify
VERIFIED via Playwright E2E (real browser, live frontend):
✓ App loads (token pre-injected)
✓ Navigate to Connectors page (More → Connectors)
✓ Find Work Email card
✓ Click Connect → form opens
✓ Enter email → IMAP host auto-detects (gmail.com → imap.gmail.com)
✓ Enter app password (masked)
✓ Click Connect & Verify → API call fires
✓ Honest error displayed (IMAP failure message visible)
✓ User stays logged in (no session-expired reload — 401→400 fix works)

Deploy: live=HEAD=f29609d, S0 holds.

## Learn
Backend verification is not UI verification. The third UI-layer failure in this arc (SSR Loading…, connector listed but not usable, work email button not working) was caught by Playwright, not by backend API testing. The standing rule: no feature is "done" until its full UI flow is verified in a JS-executing browser (Playwright). The 401→400 confusion (IMAP auth failure treated as session-auth failure) is a subtle bug that only surfaces when a real user clicks through the flow — unit tests and API tests miss it because they do not go through maestroFetch.

## Outcome
**RESOLVED**

Work email UI fixed and Playwright-verified. 401→400 (stop session-clearing). Error detail in toast. IMAP host auto-detect. App-password guidance. E2E test proves the full flow works in a real browser. Ready for Prateek to connect his real work email.

---
*This entry is append-only. Git history is the tamper-evident guarantee. The swarm never rewrites or deletes worklog entries.*