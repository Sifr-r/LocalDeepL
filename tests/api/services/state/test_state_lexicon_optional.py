"""Regression test: glossary_imports handles missing/None lexicon_store gracefully."""

from __future__ import annotations

import pytest

from omniscribe.api.routers import glossary_imports, state
from omniscribe.api.services.envelope import BackendUnavailable


def test_library_helper_raises_backend_unavailable_when_store_is_none(
    monkeypatch,
) -> None:
    """When lexicon_store is None, _library() raises BackendUnavailable with install hint."""
    monkeypatch.setattr(state, "lexicon_store", None)
    with pytest.raises(BackendUnavailable) as exc_info:
        glossary_imports._library()
    assert "uv sync --extra lexicon" in str(exc_info.value.detail)
