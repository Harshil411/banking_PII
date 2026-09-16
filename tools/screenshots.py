"""Capture the README screenshots from a running server.

Playwright is deliberately not in requirements-dev.txt: it downloads a ~100MB
browser, and CI has no use for it. Install it on demand:

    pip install playwright && python -m playwright install chromium
    make serve            # in another terminal
    make screenshots

Screenshots are taken after the page has run its default analysis, so they show
real output from the running service rather than a mock-up.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "screenshots"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"


async def main() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright is not installed; see tools/screenshots.py", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()

        async def page_for(scheme: str, width: int, height: int):
            page = await browser.new_page(
                viewport={"width": width, "height": height},
                color_scheme=scheme,
                device_scale_factor=2,
            )
            await page.goto(URL, wait_until="networkidle")
            await page.wait_for_selector(".ent")
            await page.wait_for_selector("#types tbody tr")
            await page.wait_for_timeout(400)
            # Element screenshots scroll the element to the top, where the sticky
            # header would sit on top of it. Unpin it for the capture (CSSOM, so
            # the page's CSP allows it).
            await page.evaluate("document.querySelector('.topbar').style.position = 'static'")
            return page

        for scheme in ("light", "dark"):
            page = await page_for(scheme, 1280, 800)
            await page.locator("#try .workspace").screenshot(path=OUT / f"demo-{scheme}.png")
            if scheme == "light":
                await page.locator(".evidence-grid").screenshot(path=OUT / "evidence.png")
                await page.locator("#splits").screenshot(path=OUT / "evaluation.png")
            await page.close()

        phone = await page_for("light", 390, 844)
        await phone.screenshot(path=OUT / "mobile.png")
        await browser.close()

    for path in sorted(OUT.glob("*.png")):
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
