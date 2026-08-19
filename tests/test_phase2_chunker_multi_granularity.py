"""Audit-secondary F26 / Phase 2 fix: ``_Chunker`` preserves delimiter granularity.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability.

The original fix: ``_Chunker.add`` used to overwrite its
delimiter on every call, scrambling formatting across
multi-granularity (paragraph / line / word) chunk splits.
The fix stores the delimiter alongside the chunk text so
finalize can reassemble the original spacing.
"""

from __future__ import annotations

from omniscribe.core.translation import _Chunker


def test_chunker_preserves_multi_granularity_delimiters():
    """Verify _Chunker preserves distinct paragraph and line delimiters."""
    chunker = _Chunker(max_chunk_size=100)
    chunker.add("Paragraph 1", "\n\n")
    chunker.add("Paragraph 2", "\n\n")
    chunker.add("Line 1", "\n")
    chunks = chunker.finalize()

    assert len(chunks) == 1
    assert chunks[0] == "Paragraph 1\n\nParagraph 2\nLine 1"
