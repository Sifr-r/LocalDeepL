import json
import os
import re
import sys
from pathlib import Path

from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect, sync_playwright

# Import the canonical example-PDF list from tests/conftest.py so the file
# we exercise here stays in lock-step with the parametrize sites in
# tests/test_integration.py. ``test_ui.py`` lives at the repo root rather
# than under tests/, so we add the tests/ directory to sys.path before
# importing the conftest module.
_TESTS_DIR = Path(__file__).resolve().parent / "tests"
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from conftest import EXAMPLE_PDF_NAMES  # noqa: E402

# The smoke test exercises the dense OCR path; pin the filename from the
# canonical list so removing dense.pdf from EXAMPLE_PDF_NAMES fails loud.
_DENSE_PDF_NAME = next(
    (n for n in EXAMPLE_PDF_NAMES if n == "dense.pdf"),
    None,
)
if _DENSE_PDF_NAME is None:  # pragma: no cover — guarded for the conftest audit
    raise RuntimeError(
        "test_ui.py requires 'dense.pdf' in EXAMPLE_PDF_NAMES; "
        f"current list: {EXAMPLE_PDF_NAMES}"
    )


def run() -> None:
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # Go to local server. The legacy fixed `wait_for_timeout(2000)` masked a
        # race: the file input is rendered by Svelte after the bundle parses
        # and the SPA hydrates, so wait on the actual element instead of a
        # blind sleep. `wait_for_load_state("networkidle")` covers the
        # initial /api/* config fetches the Svelte app fires on mount.
        page.goto("http://localhost:8000")
        page.wait_for_load_state("networkidle")
        expect(page.locator("input#file-input")).to_be_visible()

        # Upload a test document
        file_path = os.path.join("examples", _DENSE_PDF_NAME)
        if os.path.exists(file_path):
            page.locator("input#file-input").set_input_files(file_path)

            # The start button is disabled until the file-select handler
            # dispatches its event; wait on that transition instead of
            # a fixed 1s sleep.
            expect(page.locator("button#start-btn")).to_be_enabled()
            page.locator("button#start-btn").click()
            print("Started OCR, waiting for it to finish...")

            # Same condition as the old `wait_for_function` (process view
            # gains the `hidden` class once OCR finishes), but expressed as
            # a Playwright locator assertion so the engine polls with its
            # own auto-wait and the 180s budget applies uniformly.
            expect(page.locator("#process-view")).to_have_class(
                re.compile(r"\bhidden\b"),
                timeout=180_000,
            )
            # Let any post-completion fetches (download link, summary) settle
            # before screenshotting. `networkidle` is the right primitive
            # here: the old fixed 1s sleep was approximating the same wait
            # against non-deterministic fetch timing.
            page.wait_for_load_state("networkidle")
        else:
            print("dense.pdf not found, just taking empty screenshot.")

        # Take screenshot
        screenshot_path = os.getenv("SCREENSHOT_PATH", "screenshot.png")
        if os.path.dirname(screenshot_path):
            os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
        page.screenshot(path=screenshot_path)
        print("Screenshot saved to", screenshot_path)

        # Audit F25 (e2e half): run axe-core against the rendered DOM after
        # the OCR roundtrip completes. ``Axe`` (axe-playwright-python) wraps
        # the same axe-core rules vitest-axe uses in a11y.test.ts — any
        # WCAG 2.1 AA violation the unit tests would catch is caught here
        # too, but against the real Svelte-hydrated layout, not a
        # ``mount()`` subtree. Failures print a JSON report to stdout so
        # the maintainer can triage from the Actions log without a
        # re-run.
        axe = Axe()
        results = axe.run(page)
        if results.response.get("violations"):
            print(
                "axe-core violations:",
                json.dumps(results.response["violations"], indent=2),
            )
            raise AssertionError(
                f"axe-core found {len(results.response['violations'])} WCAG 2.1 AA "
                "violations on the rendered workstation view; see JSON dump above"
            )

        browser.close()


if __name__ == "__main__":
    run()
