"""Tests for the ``omniscribe-migrate-lexicon`` CLI exit-code contract.

These tests pin the exit-code matrix so a regression in the migration
core (or a future refactor of the CLI) does not silently flip the
contract that operators script around. See the ``--strict`` flag
discussion in ``audits/2026-08-19-secondary-validation-pass.md`` §F3
for the design rationale.

Exit codes:
    0 — ran successfully, was a clean no-op, or ``--verify-only`` confirmed
        a valid (possibly empty) live store.
    1 — migration failed or was skipped due to ambiguous state.
    2 — only with ``--strict``: ``--verify-only`` found an empty live
        store (no glossaries, no skip).

The bug being prevented: a previous version returned exit 2 for
``--verify-only`` on a valid empty ``lexicon.lance``, which made
``if omniscribe-migrate-lexicon --verify-only; then …`` fail in
fresh-install or explicit-empty-glossary setups.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from omniscribe.cli.migrate_lexicon import main
from omniscribe.core.lexicon.migration import MigrationReport

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _report(
    *,
    ran: bool = True,
    dry_run: bool = False,
    verified: bool = False,
    backup_dir: Path | None = None,
    glossaries_migrated: int = 0,
    entries_migrated: int = 0,
    chromadb_collection_found: bool = False,
    chromadb_entries_migrated: int = 0,
    skipped: bool = False,
    skip_reason: str = "",
    warnings: list[str] | None = None,
    error: str | None = None,
) -> MigrationReport:
    """Build a minimal ``MigrationReport`` for a CLI test case."""
    return MigrationReport(
        ran=ran,
        dry_run=dry_run,
        verified=verified,
        backup_dir=backup_dir,
        glossaries_migrated=glossaries_migrated,
        entries_migrated=entries_migrated,
        chromadb_collection_found=chromadb_collection_found,
        chromadb_entries_migrated=chromadb_entries_migrated,
        skipped=skipped,
        skip_reason=skip_reason,
        warnings=warnings or [],
        error=error,
    )


# ---------------------------------------------------------------------------
# Exit-code matrix
# ---------------------------------------------------------------------------


def test_exit_code_0_successful_migration() -> None:
    """A real run that wrote data exits 0."""
    report = _report(
        ran=True,
        backup_dir=Path("/tmp/backup"),
        glossaries_migrated=2,
        entries_migrated=10,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts"]) == 0


def test_exit_code_0_clean_no_op_skipped() -> None:
    """A no-op skip (already-migrated state) exits 0."""
    report = _report(
        ran=False,
        skipped=True,
        skip_reason="no legacy state",
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts"]) == 0


def test_exit_code_0_dry_run() -> None:
    """A dry-run that succeeded exits 0 (no write happened, no error)."""
    report = _report(
        ran=False,
        dry_run=True,
        glossaries_migrated=3,
        entries_migrated=15,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts", "--dry-run"]) == 0


def test_exit_code_0_verify_only_no_lexicon() -> None:
    """``--verify-only`` with no ``lexicon.lance`` to verify is exit 0.

    This is the path that the original code routed through an explicit
    ``if report.verified and report.error is None and report.skipped:
    return 0`` branch. After the fix it falls through to the final
    ``return 0`` because ``args.strict`` is False. We pin both the
    pre-fix and post-fix behavior here.
    """
    report = _report(
        ran=False,
        verified=True,
        skipped=True,
        skip_reason="no lexicon.lance to verify",
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts", "--verify-only"]) == 0


def test_exit_code_0_verify_only_empty_valid_store() -> None:
    """**The bug fix.** ``--verify-only`` on a valid empty ``lexicon.lance``
    exits 0 by default. Before the fix, this returned 2 — operators
    scripting `if omniscribe-migrate-lexicon --verify-only; then …`
    got a false-positive failure on a fresh install or one with no
    glossaries.
    """
    report = _report(
        ran=False,
        verified=True,
        glossaries_migrated=0,  # live store is empty
        entries_migrated=0,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts", "--verify-only"]) == 0


def test_exit_code_0_verify_only_populated_store() -> None:
    """``--verify-only`` on a populated store exits 0."""
    report = _report(
        ran=False,
        verified=True,
        glossaries_migrated=2,
        entries_migrated=20,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts", "--verify-only"]) == 0


def test_exit_code_1_migration_error() -> None:
    """A migration that failed with an error exits 1."""
    report = _report(
        ran=True,
        backup_dir=Path("/tmp/backup"),
        error="Cannot open LanceDB at /tmp/x.lance: permission denied",
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts"]) == 1


def test_exit_code_1_verify_only_open_error() -> None:
    """``--verify-only`` that failed to open ``lexicon.lance`` exits 1
    (the error path is checked first, before ``--strict``)."""
    report = _report(
        ran=False,
        verified=True,
        error="Cannot open lexicon.lance: file is corrupt",
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert main(["--artifact-dir", "/tmp/artifacts", "--verify-only"]) == 1


def test_exit_code_2_strict_verify_only_empty_store() -> None:
    """``--verify-only --strict`` on an empty store exits 2.

    This is the only path that returns 2 in the new contract: an
    explicit opt-in to "treat empty store as failure" for scripted
    pre-deploy checks. The default behavior is exit 0 (see the
    non-strict test above).
    """
    report = _report(
        ran=False,
        verified=True,
        glossaries_migrated=0,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert (
            main(
                [
                    "--artifact-dir",
                    "/tmp/artifacts",
                    "--verify-only",
                    "--strict",
                ]
            )
            == 2
        )


def test_strict_does_not_affect_populated_verify_only() -> None:
    """``--verify-only --strict`` on a populated store still exits 0."""
    report = _report(
        ran=False,
        verified=True,
        glossaries_migrated=3,
        entries_migrated=15,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        assert (
            main(
                [
                    "--artifact-dir",
                    "/tmp/artifacts",
                    "--verify-only",
                    "--strict",
                ]
            )
            == 0
        )


def test_strict_does_not_affect_non_verify_only() -> None:
    """``--strict`` is only meaningful with ``--verify-only``.

    A non-verify-only run with ``--strict`` should still follow the
    normal exit-code logic (0 on success, 1 on error).
    """
    report = _report(
        ran=True,
        backup_dir=Path("/tmp/backup"),
        glossaries_migrated=2,
        entries_migrated=10,
    )
    with patch(
        "omniscribe.cli.migrate_lexicon.run_migration",
        return_value=report,
    ):
        # --strict without --verify-only should be a no-op for exit codes
        assert main(["--artifact-dir", "/tmp/artifacts", "--strict"]) == 0
