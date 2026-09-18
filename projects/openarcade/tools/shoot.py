#!/usr/bin/env python3
"""Headless screenshot of the OpenArcade web UI for agent self-verification.

Uses Playwright's bundled (arm64) Chromium — NOT the system x64 Chrome, which
crashes under Rosetta on Apple Silicon. Waits for the Flutter canvas to paint
before capturing, so we never grab the loading splash.

Usage: python tools/shoot.py <url> <out.png> [settle_ms] [route]
  route (optional): keyboard nav to perform before capture, e.g.
    "Enter"            -> open detail of focused tile
    "Enter,ArrowRight" -> open detail then toggle to Controls tab
"""
from __future__ import annotations

import sys
from playwright.sync_api import sync_playwright


def shoot(url: str, out: str, settle_ms: int = 4000, route: str = "", hover: str = "") -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url, wait_until="load", timeout=60000)
        # Flutter renders into <flt-glass-pane>; wait for it, then let canvaskit paint.
        try:
            page.wait_for_selector("flt-glass-pane", timeout=30000)
        except Exception:
            pass
        # Let remote box-art network images finish fetching/decoding before capture.
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(settle_ms)
        # Optional keyboard route (the wall is keyboard-driven).
        for key in (k.strip() for k in route.split(",") if k.strip()):
            page.keyboard.press(key)
            page.wait_for_timeout(700)
        # Optional mouse hover at "x,y" (Flutter is one canvas -> hover by coordinate,
        # not selector). Lets us capture the hover lift/scale/glow state.
        if hover:
            hx, hy = (int(v) for v in hover.split(","))
            page.mouse.move(hx, hy)
            page.wait_for_timeout(900)
        page.screenshot(path=out, full_page=False)
        browser.close()
    print(f"wrote {out}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8560/"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/oa_wall.png"
    settle = int(sys.argv[3]) if len(sys.argv) > 3 else 4000
    route = sys.argv[4] if len(sys.argv) > 4 else ""
    hover = sys.argv[5] if len(sys.argv) > 5 else ""
    shoot(url, out, settle, route, hover)
