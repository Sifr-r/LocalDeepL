"""Audit-secondary F26 / Phase 2 fix: ``chunk_text`` preserves paragraph splits.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: ``chunk_text`` was splitting on a single
delimiter (``\n\n`` or ``\n``) and munging the formatting. The
fix preserves the original paragraph boundaries when the
text fits in a single chunk.
"""

from __future__ import annotations

from omniscribe.core.translation import chunk_text


def test_chunk_text_formatting_preserved():
    """Verify chunk_text preserves standard paragraph splits without mangling."""
    text = "Heading\n\nFirst paragraph with some text.\n\nSecond paragraph."
    chunks = chunk_text(text, max_chunk_size=500)
    assert len(chunks) == 1
    assert chunks[0] == text
