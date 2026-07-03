#!/usr/bin/env python3
"""Take a screenshot of every Maestro surface for the CEO's client demo.

Opens http://127.0.0.1:8765/ in headless Chromium, navigates to each
surface via navTo(), waits for content to render, and saves a PNG.

The surface list comes from maestro.js pageNames (the canonical nav map).
"""
from __future__ import annotations
import os, sys, time, json
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:4242/"
OUT_DIR = Path("/home/z/my-project/maestro-audit/MaestroAgent/download/MaestroAgent/docs/screenshots")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Canonical surface map (from static/js/maestro.js pageNames)
SURFACES = [
    ("today",          "Today — Morning Brief"),
    ("memory",         "Memory — Unified Feed"),
    ("ask-v2",         "Ask — Executive Question"),
    ("more",           "More — All Surfaces"),
    ("home",           "Home — Executive Cognition Center"),
    ("inbox",          "Inbox — Decisions Awaiting You"),
    ("simulator",      "Simulator — Decision Simulator"),
    ("hayek",          "Hayek — Knowledge Graph"),
    ("flow",           "Flow — Knowledge Flow"),
    ("ask",            "Ask — Legacy Ask"),
    ("customer",       "Customer — Judgment Engine"),
    ("physics",        "Physics — Execution Laws"),
    ("debate",         "Debate — Active Debates"),
    ("live",           "Live — Meeting Analyzer"),
    ("intents",        "Intents — Intent Cascade"),
    ("contradictions", "Contradictions"),
    ("predictions",    "Predictions — Prediction Market"),
    ("assumptions",    "Assumptions — Dangerous Assumptions"),
    ("eng-signals",    "Engineering — Signals"),
    ("eng-oem",        "Engineering — OEM Builder"),
    ("eng-audit",      "Engineering — Audit Log"),
    ("eng-settings",   "Engineering — Settings"),
    ("canvas",         "Canvas — Decision Canvas"),
    ("coordination",   "Coordination — Coordination Engine"),
    ("work",           "Work — Work Surface"),
    ("learn",          "Learn — Learn Surface"),
    ("evolution",      "Evolution — Evolution Report"),
    ("cognition",      "Cognition — Cognitive Organs"),
    ("autobiography",  "Autobiography — Org Story"),
    ("playbook",       "Playbook — Role Playbooks"),
    ("personal",       "Personal — Personal Mode"),
]


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                       device_scale_factor=2)
        page = context.new_page()
        # Capture console errors per-surface
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # Let Today surface render

        for surface_id, title in SURFACES:
            page_errors.clear()
            # Check the surface element exists in DOM before navigating
            exists = page.evaluate(
                f"() => !!document.getElementById('surface-{surface_id}')"
            )
            if not exists:
                print(f"  SKIP {surface_id:20s} — no #surface-{surface_id} element in DOM")
                results.append({"surface": surface_id, "title": title,
                                "status": "skipped", "reason": "no DOM element"})
                continue

            # Navigate + wait for content
            page.evaluate(f"window.navTo('{surface_id}')")
            page.wait_for_timeout(2500)  # Let SWR fetches resolve

            # Capture text + screenshot
            active_text = page.evaluate(
                """() => {
                    const el = document.querySelector('.surface.active');
                    return el ? (el.innerText || '').trim() : '';
                }"""
            )
            text_len = len(active_text)
            filename = f"{surface_id}.png"
            filepath = OUT_DIR / filename
            page.screenshot(path=str(filepath), full_page=False)

            status = "ok" if text_len > 50 else "thin"
            print(f"  {status:4s} {surface_id:20s} → {filename}  ({text_len} chars)"
                  + (f"  [pageerrors: {len(page_errors)}]" if page_errors else ""))
            results.append({
                "surface": surface_id, "title": title, "status": status,
                "text_len": text_len, "filename": filename,
                "page_errors": list(page_errors),
            })

        # Also screenshot the command palette (Ctrl+K)
        try:
            page.evaluate("window.navTo('today')")
            page.wait_for_timeout(1000)
            page.keyboard.press("Control+k")
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT_DIR / "command-palette.png"), full_page=False)
            print(f"  ok   command-palette       → command-palette.png")
            results.append({"surface": "command-palette", "title": "Command Palette (⌘K)",
                            "status": "ok", "filename": "command-palette.png"})
        except Exception as e:
            print(f"  FAIL command-palette: {e}")

        browser.close()

    # Write manifest
    manifest_path = OUT_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n{len(results)} surfaces captured → {OUT_DIR}")
    ok = sum(1 for r in results if r["status"] == "ok")
    thin = sum(1 for r in results if r["status"] == "thin")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    print(f"  ok={ok}  thin={thin}  skipped={skipped}")
    print(f"  manifest → {manifest_path}")


if __name__ == "__main__":
    main()
