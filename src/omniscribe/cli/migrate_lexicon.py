"""CLI entry point for ``omniscribe-migrate-lexicon``.

See ``docs/lexicon-migration-spec.md`` §6.2 for the design.

Usage
-----

::

    omniscribe-migrate-lexicon                  # run (idempotent)
    omniscribe-migrate-lexicon --dry-run       # show what would happen
    omniscribe-migrate-lexicon --verify-only   # check existing migration
    omniscribe-migrate-lexicon --artifact-dir <path>   # override default

The default ``--artifact-dir`` is read from the
``OMNISCRIBE_ARTIFACT_DIR`` env var; falls back to
``./omniscribe_artifacts`` in the current working directory.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from omniscribe.core.lexicon.migration import run_migration


def _default_artifact_dir() -> Path:
    override = os.getenv("OMNISCRIBE_ARTIFACT_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd() / "omniscribe_artifacts"


def _format_report(report) -> str:
    """Format a :class:`MigrationReport` for console output."""
    if report.verified:
        if report.error:
            return f"verify-only FAILED: {report.error}"
        return (
            "verify-only OK\n"
            f"  glossaries: {report.glossaries_migrated}\n"
            f"  entries:    {report.entries_migrated}"
        )
    if report.dry_run:
        if report.error:
            return f"dry-run FAILED: {report.error}"
        return (
            "dry-run: would migrate\n"
            f"  glossaries: {report.glossaries_migrated}\n"
            f"  entries:    {report.entries_migrated}\n"
            f"  chroma_db:  "
            f"{'present' if report.chromadb_collection_found else 'absent'} "
            f"({report.chromadb_entries_migrated} entries)"
        )
    if report.skipped:
        head = "no-op" if not report.error else "skipped (with error)"
        body = report.skip_reason
        if report.error:
            body = f"{body}\n  error: {report.error}"
        return f"{head}: {body}"
    if report.error:
        return (
            "migration FAILED\n"
            f"  error: {report.error}\n"
            f"  partial: glossaries={report.glossaries_migrated}, "
            f"entries={report.entries_migrated}\n"
            f"  backup:  {report.backup_dir or '<not created>'}"
        )
    lines = [
        "migration complete",
        f"  glossaries: {report.glossaries_migrated}",
        f"  entries:    {report.entries_migrated}",
        f"  backup:     {report.backup_dir}",
    ]
    if report.chromadb_collection_found:
        lines.append(
            f"  chroma_db:  detected ({report.chromadb_entries_migrated} entries "
            "— embeddings re-computed by the new store)"
        )
    for w in report.warnings:
        lines.append(f"  warning:    {w}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="omniscribe-migrate-lexicon",
        description=(
            "Migrate the legacy glossary library (JSON + ChromaDB) to the "
            "new LanceDB store. Idempotent; safe to re-run."
        ),
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=_default_artifact_dir(),
        help=(
            "Path to the OmniScribe artifact directory. "
            "Defaults to $OMNISCRIBE_ARTIFACT_DIR or ./omniscribe_artifacts."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute the migration plan but do not write or back up anything.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Check that a previously-completed migration is intact. Read-only.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose (INFO) logging.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "With --verify-only: treat an empty live store (0 glossaries) as a "
            "failure (exit 2). Default treats an empty store as a valid "
            "no-glossary install and exits 0."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    report = run_migration(
        artifact_dir=args.artifact_dir,
        dry_run=args.dry_run,
        verify_only=args.verify_only,
    )
    print(_format_report(report))
    # Exit codes:
    #   0 — ran successfully, was a clean no-op, or --verify-only confirmed
    #       a valid (possibly empty) live store
    #   1 — migration failed or was skipped due to ambiguous state
    #   2 — only with --strict: --verify-only found an empty live store
    #       (no glossaries, no skip). Without --strict, an empty live store
    #       is a valid no-glossary install and exits 0.
    if report.error:
        return 1
    if (
        args.strict
        and report.verified
        and not report.skipped
        and report.glossaries_migrated == 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
