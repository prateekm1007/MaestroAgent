#!/usr/bin/env python3
"""Take a screenshot of every surface for the CEO's client demo."""
import asyncio
import os
import subprocess
import sys
import time

REPO = "/home/z/my-project/maestro-audit/MaestroAgent/download/MaestroAgent"

SURFACES = [
    ("today", "Today — Morning Brief"),
    ("memory", "Memory — Unified Feed"),
    ("ask-v2", "Ask — Executive Question"),
    ("home", "Home — Executive Cognition Center"),
    ("inbox", "Inbox — Decisions Awaiting You"),
    ("simulator", "Simulator — Decision Simulator"),
    ("hayek", "Hayek — Knowledge Graph"),
    ("flow", "Knowledge Flow"),
    ("physics", "Physics — Execution Laws"),
    ("debate", "Debate — Active Debates"),
    ("customer", "Customer Judgment"),
    ("intents", "Intent Cascade"),
    ("contradictions", "Contradictions"),
    ("predictions", "Prediction Market"),
    ("assumptions", "Dangerous Assumptions"),
    ("eng-signals", "Engineering — Signals"),
    ("eng-oem", "Engineering — OEM Builder"),
    ("eng-audit", "Engineering — Audit Log"),
    ("eng-settings", "Engineering — Settings"),
    ("canvas", "Canvas — Decision Map"),
    ("personal", "Personal Mode"),
    ("work", "Work Surface"),
    ("learn", "Learn Surface"),
    ("evolution", "Evolution"),
    ("cognition", "Cognition"),
    ("autobiography", "Autobiography"),
    ("playbook", "Playbook"),
]

async def main():
    screenshot_dir = os.path.join(REPO, "docs/screenshots")
    os.makedirs(screenshot_dir, exist_ok=True)
    
    # Start the server
    env = {**os.environ, "MAESTRO_LOCAL_DEV": "true", "MAESTRO_DEMO_SEED": "true", "PYTHONPATH": "."}
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "maestro_api.main:create_app", "--factory", "--port", "1420"],
        cwd=os.path.join(REPO, "backend"),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("Starting server...")
    time.sleep(5)
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1440, "height": 900})
            
            await page.goto("http://localhost:1420/app.html")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(3000)
            
            for surface_id, title in SURFACES:
                try:
                    await page.evaluate(f"navTo('{surface_id}')")
                    await page.wait_for_timeout(2000)
                    
                    filename = os.path.join(screenshot_dir, f"{surface_id}.png")
                    await page.screenshot(path=filename, full_page=True)
                    print(f"OK {title} -> {surface_id}.png")
                except Exception as e:
                    print(f"FAIL {title}: {e}")
            
            await browser.close()
    except ImportError:
        print("Playwright not available — generating placeholder screenshots")
        # Generate placeholder images using PIL
        from PIL import Image, ImageDraw, ImageFont
        for surface_id, title in SURFACES:
            img = Image.new('RGB', (1440, 900), color=(245, 245, 245))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            except:
                font = ImageFont.load_default()
            draw.text((100, 400), f"MaestroAgent — {title}", fill=(0, 0, 0), font=font)
            draw.text((100, 450), f"Surface: {surface_id}", fill=(153, 153, 153), font=font)
            # Yellow accent bar
            draw.rectangle([(0, 0), (1440, 6)], fill=(255, 198, 41))
            filename = os.path.join(screenshot_dir, f"{surface_id}.png")
            img.save(filename)
            print(f"OK {title} -> {surface_id}.png (placeholder)")
    
    finally:
        server.terminate()
        server.wait()
    
    count = len([f for f in os.listdir(screenshot_dir) if f.endswith('.png')])
    print(f"\n{count} screenshots saved to {screenshot_dir}")

asyncio.run(main())
