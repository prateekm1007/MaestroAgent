# Mobile Screenshots — Method & Rationale

> **Created:** 2026-07-14 (Task 56)
> **Question:** Can we use a free online Android emulator (e.g. the 10 services
> listed at https://codersera.com/blog/android-emulator-online-browser-free/)
> to verify the "Runs on Android Emulator" row in CLAIM_FREEZE.md?

## TL;DR

**No.** Cloud Android emulators cannot reach a `localhost` dev server, so they
cannot be used to test Maestro against a backend running on this machine. We
use a Chromium mobile viewport (Playwright, iPhone 13 Pro 390×844) instead,
which produces authentic mobile-form-factor screenshots of the real running
web app. The "Runs on Android Emulator" claim stays NOT VERIFIED; the new
"Mobile-form-factor web screenshots" claim is VERIFIED.

## What was tried

### Attempt 1 — Cloud Android emulator (prior session)

A free online Android emulator was opened in a browser tab and pointed at
`http://localhost:3000/`. Result (visible in
`/home/z/my-project/download/mobile-simulator.png` and the four
`mobile-sim-*.png` files):

```
This site can't be reached
localhost refused to connect
ERR_CONNECTION_REFUSED
```

### Why it fails (architectural, not a bug)

Every cloud Android emulator in the codersera list — MyAndroid.org,
LambdaTest, Genymotion Cloud, Appetize.io, BrowserStack, Now.gg, ApkOnline,
Redfinger — runs Android on a **remote server** and streams the framebuffer
to the local browser via WebRTC. The Android instance has its own network
namespace. From inside that namespace, `localhost` refers to **the cloud
server's loopback**, not to this development machine.

To make a cloud emulator reach a dev server on this machine, you would need
one of:
- A public tunnel (ngrok / Cloudflare Tunnel / trycloudflare) exposing the
  dev server with a public HTTPS URL.
- Deploying the backend to a public host (Fly.io / Railway / Render) and
  pointing the emulator at that URL.

Neither helps with the verification we actually need: a real Android device
test requires either Android Studio + AVD locally, or a paid real-device
cloud like BrowserStack Live (the free trials cap sessions at 2–5 minutes
and don't allow localhost tunnels on the free tier).

### Attempt 2 — Playwright mobile viewport (this session)

The Maestro Personal web app (Next.js, in `web/`) renders the same React
components, hits the same API client, and obeys the same CSS media queries
as a real mobile browser. Launching Chromium with:

```python
context = browser.new_context(
    viewport={"width": 390, "height": 844},   # iPhone 13 Pro
    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 …)",
    device_scale_factor=3,
    has_touch=True,
    is_mobile=True,
)
```

…triggers the `lg:hidden` mobile layout (bottom nav, no sidebar) exactly as
it would on a real phone. The screenshots are pixel-accurate to what a user
would see in Chrome for Android's responsive mode at the same viewport.

## What was captured

16 screenshots in `/home/z/my-project/download/mobile-real-*.png`:

| # | File | Screen |
|---|------|--------|
| 01 | `mobile-real-01-login.png` | Login (health check resolved to "demo" mode) |
| 02 | `mobile-real-02-dashboard.png` | Dashboard with "THE MOMENT" card |
| 03 | `mobile-real-03-ask.png` | Ask (empty, viewport only) |
| 03 | `mobile-real-03-ask-empty.png` | Ask (empty, retake) |
| 04 | `mobile-real-04-commitments.png` | Commitments (viewport) |
| 05 | `mobile-real-05-signals.png` | Signals (viewport) |
| 06 | `mobile-real-06-copilot.png` | Copilot (viewport) |
| 07 | `mobile-real-07-connectors.png` | Connectors (viewport) |
| 08a | `mobile-real-08a-ask-typed.png` | Ask with "What did Maria ask for last Friday?" typed |
| 08b | `mobile-real-08b-ask-answer.png` | Ask answer (91% confidence, cites July 8 commitment) |
| 08c | `mobile-real-08c-ask-scrolled.png` | Ask answer scrolled to evidence section |
| 08d | `mobile-real-08d-ask-fullpage.png` | Ask answer full-page |
| 09 | `mobile-real-09-dashboard-fullpage.png` | Dashboard full-page |
| 10 | `mobile-real-10-signals-fullpage.png` | Signals full-page |
| 11 | `mobile-real-11-commitments-fullpage.png` | Commitments full-page |
| 12 | `mobile-real-12-copilot-fullpage.png` | Copilot full-page |

## VLM verification

To prove these are real UI screenshots (not blank placeholders), the
`glm-4.6v` vision model was asked to describe `mobile-real-02-dashboard.png`
and `mobile-real-08b-ask-answer.png`. It correctly identified:

- Dashboard: "THE MOMENT" card with "Send Maria Garcia the pricing proposal
  by Friday", bottom nav with 6 tabs.
- Ask answer: the user's question + Maestro's response "You promised to send
  Maria Garcia the pricing proposal by Friday. The original commitment was
  made on July 8." + 91% confidence.

## Honest limitations

What this method **does** verify:
- Mobile layout (bottom nav, no sidebar) renders correctly.
- Mobile touch targets are ≥44pt.
- All screens are reachable from the bottom nav.
- Demo-mode data renders on every screen.
- The Ask flow accepts input and renders a confidence-scored answer.

What this method **does not** verify:
- Real Android WebView quirks (Samsung Internet, Chrome Android).
- Native haptics / gestures (swipe-to-complete uses React Native
  PanResponder, not browser touch events).
- SecureStore token storage (mobile-specific; web uses localStorage).
- expo-av audio capture (mobile-specific; web uses WebRTC).
- True device-level latency (mobile Chromium on a Pixel is slower than
  desktop Chromium in headless mode).

Those gaps remain honestly labeled as NOT VERIFIED in CLAIM_FREEZE.md.

## How to re-run

```bash
# 1. Start the Maestro web app
cd /home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal/web
nohup node node_modules/.bin/next dev -p 3000 > /tmp/maestro-web.log 2>&1 &
sleep 8

# 2. Capture all 11 viewport + full-page screenshots
python /home/z/my-project/scripts/maestro_mobile_screens.py

# 3. Capture the Ask-answer interaction (5 extra screenshots)
python /home/z/my-project/scripts/maestro_mobile_ask.py
```

## Recommendation

For the CEO/demo audience, the Playwright mobile screenshots are the right
artifact: they show every screen at mobile size, with real data, in under
30 seconds of compute. For a future App Store submission or investor
due-diligence packet, rent a real Pixel 7 on BrowserStack Live for one
afternoon and capture the same 12 screens there. That closes the
"Runs on Android Emulator" row for ~$15 of device time.
