#!/usr/bin/env python3
"""Check mode/quality transitions against a running viewer and a moderate STEP.

Uses the viewer's public diagnostic snapshots. No model builds or downloads;
install requirements-dev.txt and Playwright Chromium before running this check.
"""

import argparse
import json
import sys

from playwright.sync_api import sync_playwright


STATE = """() => ({
  lod: window.__cadViewportLod?.(), quality: window.__cadViewerQuality,
  badge: document.querySelector('[data-file-status]')?.dataset.fileStatus
})"""
SETTLED = """expected => {
  const lod = window.__cadViewportLod?.();
  const quality = window.__cadViewerQuality;
  return lod?.componentCount > 0 && lod.quality === expected && lod.qualitySettled &&
    quality?.quality === expected && quality.standardQualityReady &&
    (expected !== 'high' || quality.highQualityReady);
}"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Viewer URL with ?file= pointing to a moderate STEP assembly")
    args = parser.parse_args()
    with sync_playwright() as playwright:
        flags = ["--ignore-gpu-blocklist"]
        if sys.platform == "darwin":
            flags.append("--use-angle=metal")
        browser = playwright.chromium.launch(headless=True, args=flags)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settled(expected):
            page.wait_for_function(SETTLED, arg=expected, timeout=30000)
            state = page.evaluate(STATE)
            assert state.get("badge") is None, state
            print(json.dumps({"quality": expected, "levels": state["lod"]["levelCounts"],
                              "badge": state.get("badge")}), flush=True)

        def mode(current, next_mode):
            page.get_by_role("button", name=f"Viewing mode: {current}", exact=True).click()
            page.get_by_role("menuitemradio", name=next_mode, exact=True).click()

        try:
            page.goto(args.url, wait_until="domcontentloaded")
            settled("interactive")
            for _ in range(2):
                mode("Inspect", "Render")
                # No camera gesture: a newly constructed Render scene must
                # trigger refinement itself, not wait indefinitely for orbit.
                settled("high")
                for label, expected in (("Preview", "standard"), ("Final", "high")):
                    page.get_by_role("combobox", name="Quality", exact=True).click()
                    page.get_by_role("option", name=label, exact=True).click()
                    settled(expected)
                page.mouse.move(420, 400)
                page.mouse.down()
                page.mouse.move(600, 460, steps=12)
                page.mouse.up()
                settled("high")
                mode("Render", "Inspect")
                settled("interactive")
            assert not errors, errors
        except Exception:
            print(json.dumps(page.evaluate(STATE)), file=sys.stderr)
            raise
        finally:
            browser.close()


if __name__ == "__main__":
    main()
