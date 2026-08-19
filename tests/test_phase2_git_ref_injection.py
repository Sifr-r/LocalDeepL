"""Audit-secondary F26 / Phase 2 fix: git ``ref`` is validated against flag injection.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: ``parse_git_glossary`` passed the ``ref``
parameter directly to ``git archive``, which is vulnerable
to flag injection (``--output=/tmp/pwn``) and shell metachar
injection (``HEAD; rm -rf /``). The fix validates the ref
against a safe-character set before passing it to git.
"""

from __future__ import annotations

import pytest

from omniscribe.core.glossary_sources.git_repo import parse_git_glossary


def test_git_glossary_ref_flag_injection_rejected():
    """Verify git archive rejects flag arguments in ref parameter."""
    with pytest.raises(ValueError, match="Git ref is invalid or malformed"):
        parse_git_glossary(
            url="https://github.com/org/repo.git", ref="--output=/tmp/pwn"
        )

    with pytest.raises(ValueError, match="Git ref is invalid or malformed"):
        parse_git_glossary(url="https://github.com/org/repo.git", ref="-f")

    with pytest.raises(ValueError, match="Git ref is invalid or malformed"):
        parse_git_glossary(url="https://github.com/org/repo.git", ref="HEAD; rm -rf /")
