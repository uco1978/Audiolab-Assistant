"""Playwright fallback for JS-rendered manufacturer pages."""

from __future__ import annotations


async def fetch_with_playwright(url: str, timeout_ms: int = 30000) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            await page.wait_for_timeout(1500)
            return await page.content()
        finally:
            await browser.close()
