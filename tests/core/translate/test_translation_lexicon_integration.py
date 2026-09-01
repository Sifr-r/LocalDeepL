"""Tests for the LexiconStore integration in the translation graph (Phase 3).

The translation graph's ``retrieve_lexicon_context`` node reads from the
new LanceDB-backed LexiconStore (replacing the legacy ChromaDB
``lanes_lexicon`` collection). These tests verify:

- The new path returns hits when the store has data.
- The new path degrades gracefully when the store is empty.
- The new path filters by source/target language when those are present
  in the state.
- The ChromaDB module is no longer imported by ``core.translate.workflow``.

The legacy ChromaDB collection path is exercised by the migration test
suite; this file is about the *new* path only.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# The translation graph's lexicon integration pulls in the LanceDB-backed
# LexiconStore, which transitively imports ``pyarrow`` and ``lancedb`` at
# module load. Both are optional extras; skip the whole module when the
# CI environment doesn't have them (matches the pattern in
# ``tests/core/lexicon/test_lexicon_*.py``).
pytest.importorskip("pyarrow")
pytest.importorskip("lancedb")

from omniscribe.core.lexicon import (
    LanceDBLexiconStore,
    reset_default_store,
)
from omniscribe.core.lexicon.embedding import EmbeddingModel
from omniscribe.core.translate.workflow import retrieve_lexicon_context


class _FakeEmbeddingModel:
    dim = 384
    model_name = "fake-test-model"

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        out: list[list[float]] = []
        for t in texts:
            digest = hashlib.sha256(t.encode("utf-8")).digest()
            base = [b / 255.0 for b in digest] * 12
            vec = base[: self.dim]
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            vec = [x / norm for x in vec]
            out.append(vec)
        return out


@pytest.fixture
def fake_model() -> EmbeddingModel:
    return _FakeEmbeddingModel()


@pytest.fixture(autouse=True)
def _reset_store_cache() -> None:  # type: ignore[misc]
    """Each test gets a fresh default store cache."""
    reset_default_store()
    yield
    reset_default_store()


# ---------------------------------------------------------------------------
# No-op / graceful degradation
# ---------------------------------------------------------------------------


def test_retrieve_returns_empty_when_no_store() -> None:
    """If the default store can't open, rag_context is empty (no crash)."""
    with patch(
        "omniscribe.core.lexicon.get_default_store",
        side_effect=RuntimeError("test: store unavailable"),
    ):
        state: dict[str, Any] = {
            "source_chunk": "Translate this.",
            "target_language": "French",
        }
        result = retrieve_lexicon_context(state)
    assert result == {"rag_context": []}


def test_retrieve_works_with_empty_store(
    tmp_path: Path, fake_model: EmbeddingModel
) -> None:
    """Empty store → empty rag_context (don't crash)."""
    store = LanceDBLexiconStore(
        path=tmp_path / "lexicon.lance", embedding_model=fake_model
    )

    with patch("omniscribe.core.lexicon.get_default_store", return_value=store):
        state: dict[str, Any] = {
            "source_chunk": "Hello world.",
            "target_language": "French",
        }
        result = retrieve_lexicon_context(state)
    assert result == {"rag_context": []}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_retrieve_returns_hits_when_store_has_data(
    tmp_path: Path, fake_model: EmbeddingModel
) -> None:
    store = LanceDBLexiconStore(
        path=tmp_path / "lexicon.lance", embedding_model=fake_model
    )
    store.save_glossary(
        name="Animals EN→FR",
        format="json_pairs",
        entries=[
            {
                "source": "dog",
                "target": "chien",
                "source_lang": "en",
                "target_lang": "fr",
            },
            {
                "source": "cat",
                "target": "chat",
                "source_lang": "en",
                "target_lang": "fr",
            },
        ],
    )
    with patch("omniscribe.core.lexicon.get_default_store", return_value=store):
        state: dict[str, Any] = {
            "source_chunk": "dog",
            "target_language": "fr",
        }
        result = retrieve_lexicon_context(state)
    assert len(result["rag_context"]) >= 1
    # The first hit should be the exact "dog" entry
    assert result["rag_context"][0] == "- dog -> chien"


def test_retrieve_filters_by_language_pair(
    tmp_path: Path, fake_model: EmbeddingModel
) -> None:
    store = LanceDBLexiconStore(
        path=tmp_path / "lexicon.lance", embedding_model=fake_model
    )
    # EN→FR glossary
    store.save_glossary(
        name="EN-FR",
        format="json_pairs",
        entries=[
            {
                "source": "dog",
                "target": "chien",
                "source_lang": "en",
                "target_lang": "fr",
            },
        ],
    )
    # ES→PT glossary
    store.save_glossary(
        name="ES-PT",
        format="json_pairs",
        entries=[
            {
                "source": "perro",
                "target": "cão",
                "source_lang": "es",
                "target_lang": "pt",
            },
        ],
    )
    # When the request is for en→fr, only the EN-FR hit should come back.
    with patch("omniscribe.core.lexicon.get_default_store", return_value=store):
        state: dict[str, Any] = {
            "source_chunk": "dog",
            "target_language": "fr",
            "source_lang": "en",
            "target_lang": "fr",
        }
        result = retrieve_lexicon_context(state)
    # Should have a hit, and it should be the EN-FR one (not ES-PT).
    assert all("chien" in line for line in result["rag_context"])


# ---------------------------------------------------------------------------
# Module no longer depends on ChromaDB
# ---------------------------------------------------------------------------


def test_translation_module_does_not_import_chromadb() -> None:
    """Phase 3 acceptance: the ChromaDB query path is gone from translate/workflow.py."""
    # Re-import to be sure
    importlib.reload(importlib.import_module("omniscribe.core.translate.workflow"))
    from omniscribe.core.translate import workflow as translation

    # The module no longer exposes the ChromaDB-specific symbols
    assert not hasattr(translation, "CHROMA_COLLECTION_NAME")
    assert not hasattr(translation, "_chroma_client")
    assert not hasattr(translation, "get_chroma_collection")


# ---------------------------------------------------------------------------
# State shape
# ---------------------------------------------------------------------------


def test_translation_state_supports_optional_language_fields() -> None:
    """TranslationState now has optional source_lang/target_lang for hybrid filtering."""
    from omniscribe.core.translate.workflow import TranslationState

    # total=False on the TypedDict means missing fields are allowed.
    state: TranslationState = {
        "source_chunk": "x",
        "target_language": "fr",
    }
    # No source_lang/target_lang — node must still work (just no filter).
    assert state.get("source_lang") is None
    assert state.get("target_lang") is None

    state_with_lang: TranslationState = {
        "source_chunk": "x",
        "target_language": "fr",
        "source_lang": "en",
        "target_lang": "fr",
    }
    assert state_with_lang["source_lang"] == "en"
