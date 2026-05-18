"""Headless smoke test — verifies all sections render without JS errors."""
import sys
from playwright.sync_api import sync_playwright

URL = "http://localhost:8765/index.html"

errors = []
console_msgs = []

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.on("pageerror", lambda exc: errors.append(f"PAGE ERROR: {exc}"))
    page.on("console", lambda msg: (console_msgs.append(f"{msg.type}: {msg.text}")
                                    if msg.type in ("error", "warning") else None))

    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(800)

    # check that the dashboard chart canvas exists
    assert page.locator("#dash-bh-chart").is_visible(), "dashboard chart missing"

    sections = ["stocks", "strategies", "temporal", "pairs", "summary"]
    for s in sections:
        page.click(f'.nav-item[data-section="{s}"]')
        page.wait_for_timeout(500)
        assert page.locator(f"#section-{s}").is_visible(), f"section {s} not visible"

    # Probe each canvas was drawn (Chart.js sets canvas role and has non-zero size)
    canvases = page.evaluate("""
      Array.from(document.querySelectorAll('canvas')).map(c => ({
        id: c.id, w: c.width, h: c.height
      }))
    """)
    browser.close()

print("Canvases drawn:")
for c in canvases:
    ok = c["w"] > 0 and c["h"] > 0
    print(f"  {'OK' if ok else 'NO'}  {c['id']:<22}  {c['w']}x{c['h']}")

if errors:
    print("\nERRORS:")
    for e in errors:
        print(" ", e)
if console_msgs:
    print("\nConsole errors/warnings:")
    for m in console_msgs:
        print(" ", m)

if errors:
    sys.exit(1)
print("\nSmoke test passed.")
