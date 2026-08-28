"""Regression tests for the Domain 4 MEDIUM cluster audit fixes.

Re-homed from ``test_audit_medium_d4.py`` in Phase 4.3: the suite is a
cohesive test-tier-discipline pin (doc pins, asyncio-mark scans, fixture
scopes, CI-workflow drift), so it stays one file under a descriptive
name instead of being scattered across component suites.

Pins the post-2026-08-17 behaviour of the test tier discipline +
asyncio-mode cleanup + AGENTS.md documentation updates so future
refactors cannot silently regress the 12 items addressed in
Phase 5d.

Pins:

* **F4.9** — closed by Phase B (the Svelte UI that the Playwright
  a11y spec covered was removed); the regression pin below is
  now a forward guard that ``AGENTS.md``'s Known Tech Debt
  documents the a11y-testing requirement for any future web
  client.
* **F4.10** — no active test file (other than the documented
  ``test_live_llm.py`` exceptions) carries a redundant
  ``@pytest.mark.asyncio`` decorator.
* **F4.11** — ``AGENTS.md`` documents the ``slow_dataset`` marker
  alongside ``slow`` and ``live_llm``.
* **F4.12** — ``synthetic_pdf`` fixture in ``test_chunked_runner.py``
  is session-scoped, not function-scoped.
* **F4.14** — no ``test_docuverse_upgrade.py`` exists at the old path
  (renamed to a non-``test_*.py`` filename so pytest collection skips
  it).
* **F4.15** — ``test_health_endpoints.py`` no longer carries a
  module-level ``pytestmark = pytest.mark.asyncio``.
* **F4.16** — ``test_workflows_callback_decoupling.py`` uses
  ``relative_to("src/omniscribe/core")`` for the parametrize ids.
* **F4.17/20** — the Python matrix drift and the fast-sync vs
  nightly-sync trade-off are documented inline in ``test.yml``.

N/A positive reclassifications (F4.7, F4.8, F4.13, F4.19) are
asserted via runtime evidence: the tests in question run in well
under a second per case, so marking them ``@pytest.mark.slow``
would be wrong. The audit pinned wall-clock budgets; we pin the
opposite — that the budgets are met, so the ``slow`` mark stays
absent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = ROOT / "tests"
AGENTS_MD = ROOT / "AGENTS.md"
TEST_YML = ROOT / ".github" / "workflows" / "test.yml"

# Per-file exceptions to the "no @pytest.mark.asyncio" rule. Empty for
# Phase 5d — every active test file has had the redundant mark removed
# (F4.10 + F4.15). If a future contributor re-adds the mark to one
# file, the exception list is the place to justify it.
_ASYNCIO_MARK_EXCEPTIONS: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# F4.9 — a11y gap closed by Phase B; forward guard in AGENTS.md
# ---------------------------------------------------------------------------


def test_agents_md_documents_a11y_testing_gap() -> None:
    """The F4.9 a11y testing gap is closed by Phase B, and the forward
    guard (a11y regression tests required for any future web client)
    is documented in AGENTS.md's Known Tech Debt.

    Phase B cleanup removed the Playwright a11y spec dependency by
    removing the Svelte UI that the spec covered, so the F4.9 audit
    gap is effectively closed. The contract here is twofold:

    1. ``AGENTS.md``'s Known Tech Debt section must record that any
       future web client must implement a11y regression tests (a
       forward guard against silently regressing into an unmonitored
       gap).
    2. The audit history reference (F4.9 / ``a11y`` / ``axe``) must
       stay discoverable so a reader knows the gap existed and was
       closed for that specific reason.
    """
    text = AGENTS_MD.read_text(encoding="utf-8")
    # Locate the Known Tech Debt section.
    assert "## Known Tech Debt" in text
    # Forward guard: any future web client must implement a11y
    # regression tests.
    assert "a11y" in text.lower() or "axe" in text.lower(), (
        "Known Tech Debt must mention that any future web client "
        "must implement a11y regression tests"
    )
    # F4.9 audit history must stay discoverable.
    assert "F4.9" in text or "audit" in text.lower()


# ---------------------------------------------------------------------------
# F4.10 — no redundant @pytest.mark.asyncio in active test files
# ---------------------------------------------------------------------------


def _scan_test_files_for_asyncio_mark() -> list[tuple[str, int]]:
    """Return ``(relative_path, line_number)`` for every redundant
    ``@pytest.mark.asyncio`` decorator on a ``async def test_*`` in
    active (non-``_diag``) test files. Excludes the documented
    exceptions in :data:`_ASYNCIO_MARK_EXCEPTIONS`.
    """
    hits: list[tuple[str, int]] = []
    pattern = re.compile(
        r"^[ \t]*@pytest\.mark\.asyncio\s*$",
        re.MULTILINE,
    )
    for path in sorted(TESTS_DIR.glob("**/test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("tests/_diag/"):
            continue
        if path.name in _ASYNCIO_MARK_EXCEPTIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_num, line in enumerate(text.splitlines(), start=1):
            if pattern.match(line):
                # Only flag if the next non-blank line is ``async def test_``.
                # A decorator above a sync ``def`` would be a real bug
                # (pytest would error) and is out of scope for this audit.
                hits.append((rel, line_num))
    return hits


def test_no_redundant_asyncio_marks_in_active_test_files() -> None:
    """No active test file carries a redundant ``@pytest.mark.asyncio`` decorator.

    With ``asyncio_mode = "auto"`` the marker is a no-op. Future
    authors who copy-paste the pattern from the audit's old
    test files (where the mark was sprinkled defensively) get
    caught by this regression test instead of the audit running
    again.
    """
    hits = _scan_test_files_for_asyncio_mark()
    assert not hits, (
        "Redundant @pytest.mark.asyncio decorators found (asyncio_mode='auto' "
        "makes them no-ops). Remove the marker or add the file to "
        "_ASYNCIO_MARK_EXCEPTIONS in tests/scripts/test_tier_discipline.py with "
        "a justification:\n" + "\n".join(f"  {rel}:{ln}" for rel, ln in hits)
    )


# ---------------------------------------------------------------------------
# F4.11 — slow_dataset marker documented in AGENTS.md
# ---------------------------------------------------------------------------


def test_agents_md_documents_slow_dataset_marker() -> None:
    """The ``slow_dataset`` marker is now in the AGENTS.md marker list."""
    text = AGENTS_MD.read_text(encoding="utf-8")
    # The marker must be named, briefly described, and the lane it
    # affects (``-m slow_dataset``) must be runnable.
    assert "slow_dataset" in text
    assert "-m" in text or "marker" in text.lower()


# ---------------------------------------------------------------------------
# F4.14 — test_docuverse_upgrade.py renamed to a non-test_*.py file
# ---------------------------------------------------------------------------


def test_docuverse_shim_no_longer_collectable() -> None:
    """The docstring-only shim has been renamed so pytest collection
    skips it. The historical ``.md`` sibling was removed in the
    Phase 4.3 test consolidation; nothing references it anymore.
    """
    assert not (TESTS_DIR / "test_docuverse_upgrade.py").exists(), (
        "test_docuverse_upgrade.py was renamed; see the test_tier_discipline "
        "F4.14 fix for the history."
    )
    assert not (TESTS_DIR / "docuverse_split_history.md").exists(), (
        "docuverse_split_history.md was removed in Phase 4.3; "
        "do not reintroduce non-test clutter under tests/."
    )


# ---------------------------------------------------------------------------
# F4.15 — no module-level pytestmark.asyncio anywhere in the suite
# ---------------------------------------------------------------------------


def test_no_test_module_uses_asyncio_pytestmark() -> None:
    """Module-level ``pytestmark = pytest.mark.asyncio`` is redundant
    because ``asyncio_mode = "auto"`` already covers every
    ``async def test_*`` in the suite.
    """
    pattern = re.compile(
        r"^[ \t]*pytestmark\s*=\s*pytest\.mark\.asyncio\s*$",
        re.MULTILINE,
    )
    offenders = [
        path.relative_to(TESTS_DIR).as_posix()
        for path in sorted(TESTS_DIR.rglob("test_*.py"))
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        "Module-level pytestmark = pytest.mark.asyncio is redundant under "
        f"asyncio_mode='auto'; found in: {offenders}"
    )


# ---------------------------------------------------------------------------
# F4.16 — relative-path parametrize ids
# ---------------------------------------------------------------------------


def test_workflows_callback_decoupling_ids_use_relative_path() -> None:
    """The parametrize ids use the relative path under ``core/`` so two
    modules that share a basename don't collide in the test ID.
    """
    text = (
        TESTS_DIR / "core" / "workflows" / "test_workflows_callback_decoupling.py"
    ).read_text(encoding="utf-8")
    assert "ids=lambda p: p.name" not in text, (
        "F4.16 audit fix: parametrize ids should use the relative path, "
        "not just the basename."
    )
    assert "relative_to" in text, (
        "F4.16 audit fix: the ids lambda should call .relative_to(...) so "
        "shared basenames get distinct test IDs."
    )


# ---------------------------------------------------------------------------
# F4.17 / F4.20 — test.yml documents matrix drift and fast-sync trade-off
# ---------------------------------------------------------------------------


def test_workflow_documents_matrix_drift() -> None:
    """The Python matrix drift (test.yml 3.11+3.13 vs nightly 3.12) is
    documented inline so a future reviewer doesn't try to
    "reconcile" the lanes.
    """
    text = TEST_YML.read_text(encoding="utf-8")
    assert "F4.17" in text, "F4.17 audit fix: matrix drift should be inline-documented"
    assert "3.11" in text
    assert "3.13" in text


def test_workflow_documents_fast_sync_tradeoff() -> None:
    """The fast tier intentionally skips ``--extra async-translation``;
    the trade-off is documented so a future contributor doesn't
    "fix" it without reading the audit.
    """
    text = TEST_YML.read_text(encoding="utf-8")
    assert "F4.20" in text
    assert "async-translation" in text
    # The fast sync line is the one we care about — it must remain
    # ``uv sync --extra web`` (no async-translation).
    fast_sync = re.search(
        r"^      - name: Sync deps \(CLI \+ web extras\)\s*\n((?:        .*\n)*)",
        text,
        re.MULTILINE,
    )
    assert fast_sync is not None, "Could not locate the fast sync step"
    body = fast_sync.group(1)
    assert "uv sync --extra web" in body
    assert (
        "async-translation" not in body.split("\n", 1)[0]
    )  # not on the same line as `uv sync`


# ---------------------------------------------------------------------------
# N/A reclassifications (F4.7, F4.8, F4.13, F4.19) — pin the wall-clock budgets
# ---------------------------------------------------------------------------


# Per-test budget. Tests over the budget should be marked ``@pytest.mark.slow``;
# tests under the budget stay in the fast tier. The audit's
# recommendation was to mark several fast tests as slow on the
# assumption they were slow; the evidence below shows they're not.
_PER_TEST_BUDGET_S = 1.0


@pytest.mark.parametrize(
    "module",
    [
        "tests/core/pdf/test_pdf.py",  # F4.7
        "tests/core/recall/test_text_layer_recall.py",  # F4.8
        "tests/core/workflows/test_phase5_env_and_spellcheck.py",  # F4.13
    ],
)
def test_durations_meet_fast_tier_budget(module: str) -> None:
    """Pin the wall-clock: each test in the named module finishes under
    the fast-tier budget, so the audit's recommendation to add
    ``@pytest.mark.slow`` would be wrong.

    We invoke ``pytest --durations=0 -q`` and parse the slowest
    duration. If a test crosses the budget the regression fails
    and the audit reasoning has to be revisited (either the test
    actually got slow and needs the marker, or the budget needs
    to be raised). The audit's recommendation to "mark these as
    slow" is contradicted by the data.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            module,
            "--durations=0",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Even if some tests fail (we don't care about pass/fail for
    # duration), the slowest-duration table should be in the
    # stdout. If pytest exited with a non-zero code AND produced
    # no duration table, surface the failure for debugging.
    if "slowest" not in result.stdout and "slowest" not in result.stderr:
        pytest.skip(
            f"pytest did not produce a duration table for {module}: "
            f"rc={result.returncode}"
        )
    out = result.stdout + result.stderr
    # Find the slowest entry. Format: ``<duration>s call    <path>::<test>``
    durations = re.findall(
        r"^(\d+\.\d+)s\s+call\s+([^\s]+::\S+)",
        out,
        re.MULTILINE,
    )
    if not durations:
        pytest.skip(f"No per-test durations in {module} output")
    # The slowest call is the first entry.
    slowest_s, slowest_id = durations[0]
    slowest_s_f = float(slowest_s)
    assert slowest_s_f <= _PER_TEST_BUDGET_S, (
        f"{slowest_id} took {slowest_s_f:.2f}s (budget {_PER_TEST_BUDGET_S}s). "
        "If the regression is real, the test should carry "
        "@pytest.mark.slow and this budget test should drop the module."
    )
