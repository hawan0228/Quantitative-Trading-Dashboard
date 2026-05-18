"""Capture screenshots of each dashboard section."""
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/index.html"
OUT = Path("screenshots"); OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(800)
    for s in ["dashboard", "stocks", "strategies", "temporal", "pairs", "summary"]:
        page.click(f'.nav-item[data-section="{s}"]')
        page.wait_for_timeout(700)
        page.screenshot(path=str(OUT / f"{s}.png"), full_page=True)
        print(f"saved {s}.png")
    browser.close()
