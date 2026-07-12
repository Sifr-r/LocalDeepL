"""
Frontend smoke tests.

Two goals, both designed to catch the "PR compiles but the UI is
silently broken at runtime" failure mode the JS code base has hit
before (the static/js/windowDrag.js wrong-relative-path bug):
  1. ``index.html`` references to ``/static/*`` must resolve to actual
     files on disk. Bad paths surface here, not in the browser.
  2. Each ``.js`` file in ``static/js/`` must parse cleanly under
     ``node --check``. Adds a syntax-only gate that runs in CI without
     a browser.

JS modules in this project are browser ES and use ``window``/``fetch``
at top level, so we deliberately avoid booting them in Node. The
HTML-wiring test plus ``node --check`` cover the two most common
production-busting bugs at near-zero cost.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "src" / "local_deepl" / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# External hosts we explicitly whitelist in ``index.html``. Anything not
# in here is treated as a broken link if it's local-looking (``/static/...``).
_ALLOWED_EXTERNAL_HOSTS = frozenset(
    {
        "fonts.googleapis.com",
        "fonts.gstatic.com",
        # markdown-it CDN (Phase 1 — proper markdown rendering)
        "cdn.jsdelivr.net",
    }
)


_SCRIPT_RE = re.compile(
    r"""<script[^>]+src=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)
_STYLESHEET_RE = re.compile(
    r"""<link[^>]+rel=["']stylesheet["'][^>]+href=["']([^"']+)["'][^>]*>""",
    re.IGNORECASE,
)


def _strip_cache_buster(url: str) -> str:
    """Remove the ``?v=N`` cache buster so the on-disk lookup is clean."""
    return url.split("?", 1)[0]


def _is_local(url: str) -> bool:
    return url.startswith("/") and not url.startswith("//")


def test_static_html_references_resolve_to_disk():
    """Every ``src``/``href`` that points at ``/static/...`` must exist."""
    html = INDEX_HTML.read_text(encoding="utf-8")

    referenced: list[str] = []
    for url in _SCRIPT_RE.findall(html) + _STYLESHEET_RE.findall(html):
        if not _is_local(url):
            continue
        clean = _strip_cache_buster(url)
        if not clean.startswith("/static/"):
            continue
        referenced.append(clean)

    assert referenced, "no local static references found in index.html"

    for url in referenced:
        relative = url.lstrip("/")  # ''static/...'' on disk
        target = ROOT / "src" / "local_deepl" / relative
        assert target.is_file(), (
            f"{url} referenced in index.html but missing on disk (looked at {target})"
        )


def test_static_html_external_links_use_allowlisted_hosts():
    """Any non-local URL must point at the explicit Google Fonts hosts.

    Catches the "I accidentally pasted a JS bundle URL into the
    template" mistake that would otherwise leak a public CDN.
    """
    html = INDEX_HTML.read_text(encoding="utf-8")

    for url in _SCRIPT_RE.findall(html) + _STYLESHEET_RE.findall(html):
        if _is_local(url):
            continue
        parsed = urlparse(url)
        host_part = parsed.hostname or ""
        assert host_part in _ALLOWED_EXTERNAL_HOSTS, (
            f"index.html references non-whitelisted host: {url}"
        )


def test_static_js_passes_node_check():
    """Each JS file under ``static/js/`` must parse with ``node --check``.

    Skipped when Node is not installed (the test is CI-only by design,
    but local Windows installs may not have Node on PATH).
    """
    if shutil.which("node") is None:
        pytest.skip("node not installed; install Node 18+ to enable this check")

    js_dir = STATIC_DIR / "js"
    assert js_dir.is_dir(), f"missing JS directory: {js_dir}"
    js_files = sorted(js_dir.glob("*.js"))
    assert js_files, "no JS files to check"

    failures: list[tuple[Path, str]] = []
    for js_file in js_files:
        result = subprocess.run(
            ["node", "--check", str(js_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            failures.append((js_file, result.stderr or result.stdout))

    assert not failures, "node --check failed for: " + ", ".join(
        f"{p.name}: {err.strip()}" for p, err in failures
    )
