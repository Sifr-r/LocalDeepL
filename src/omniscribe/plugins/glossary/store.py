"""Lazy LexiconStore provider (optional `lexicon` extra).

`lancedb_store.py` hard-imports pyarrow at module top, so neither it nor
`omniscribe.core.lexicon` may be imported at THIS module's top level —
the plugin must boot in images without the lexicon extra. The provider
defers the runtime import to first use; routes surface 503 with the old
install hint when the store cannot be imported.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omniscribe.core.lexicon import LexiconStore

_LOGGER = logging.getLogger("omniscribe.plugins.glossary")

LEXICON_INSTALL_HINT = (
    "Lexicon store is not available. Install with: uv sync --extra lexicon"
)


class LexiconProvider:
    """Constructs the LanceDB store on first use; caches the result."""

    def __init__(self, store_path: Path) -> None:
        self._store_path = store_path
        self._store: LexiconStore | None = None
        self._tried = False

    def get(self) -> LexiconStore | None:
        if not self._tried:
            self._tried = True
            try:
                from omniscribe.core.lexicon import LanceDBLexiconStore

                self._store = LanceDBLexiconStore(path=self._store_path)
                _LOGGER.info("lexicon store ready at %s", self._store_path)
            except ImportError as exc:
                _LOGGER.warning("lexicon extra unavailable: %s", exc)
                self._store = None
        return self._store


def null_provider() -> Callable[[], LexiconStore | None]:
    return lambda: None
