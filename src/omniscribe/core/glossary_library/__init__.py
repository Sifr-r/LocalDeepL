"""Named glossary library exports.

DEPRECATED (Phase 1, 2026-08-17): replaced by
:mod:`omniscribe.core.lexicon`. This module is kept as a re-export
surface through Phase 5 cleanup. New code should use
:class:`omniscribe.core.lexicon.GlossaryLibraryAdapter` to bridge
the old API to the new :class:`~omniscribe.core.lexicon.LexiconStore`.
"""

from .library import GlossaryLibrary, GlossaryNotFoundError, StoredGlossary

__all__ = ["GlossaryLibrary", "GlossaryNotFoundError", "StoredGlossary"]
