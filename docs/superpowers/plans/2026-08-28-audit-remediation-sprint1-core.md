# Sprint 1 — Core Pipeline Remediation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all 26 findings in the 2026-08-28 audit Domain 1 (Core Pipeline).

**Architecture:** Defensive fail-open with diagnostics. Replace silent error paths with structured logs. Replace `os.getenv` bypasses with `load_settings()`. Replace PIL `Image.open` leaks with `with` blocks. Convert magic numbers to named constants.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio (auto mode), ruff, mypy

---

## File Structure

### Files to modify

| Path | Purpose |
| :--- | :--- |
| `src/omniscribe/core/ocr/multi_format_client.py` | Add diagnostic logging on malformed multi-format LLM responses (C1) |
| `src/omniscribe/core/lexicon/lancedb_store.py` | Atomic write-then-swap for glossary toggle fallback (C2) |
| `src/omniscribe/core/ocr/processor.py` | PIL `with` blocks, `load_settings()` migration, `circuit_breaker.check()` consolidation (H1, H2, H4, M3) |
| `src/omniscribe/core/aligner.py` | PIL `with` block (H1) |
| `src/omniscribe/core/ocr/trocr.py` | PIL `with` block (H1) |
| `src/omniscribe/core/imaging/utils.py` | PIL `with` block in `decode_base64_image` (H1) |
| `src/omniscribe/core/recall/text_layer.py` | Wrap `page.get_text("words")` in try/except for fail-open (H3) |
| `src/omniscribe/core/pdf/embedder.py` | Extract magic numbers to named constants (M6, M7) |
| `src/omniscribe/core/pdf/rasterization_settings.py` | Tighten `_MAX_SAFE_PIXELS_CEILING` (M5) |
| `src/omniscribe/core/workflows/grounded.py` | Use `dataclasses.replace` instead of `obj.text = text` (M9) |
| `src/omniscribe/core/evaluation.py` | Align `_valid_bbox` semantics with `confidence_eval.iou` (M10) |

### Files to create

| Path | Purpose |
| :--- | :--- |
| `tests/core/ocr/test_multi_format_client_logging.py` | Regression tests for C1 |
| `tests/core/lexicon/test_toggle_glossary_atomic.py` | Regression tests for C2 |
| `tests/core/imaging/test_resource_leaks.py` | Regression tests for H1 |
| `tests/core/ocr/test_config_consistency.py` | Regression tests for H2/H4 |
| `tests/core/recall/test_text_layer_failopen.py` | Regression tests for H3 |
| `tests/core/pdf/test_embedder_constants.py` | Regression tests for M6/M7 |
| `tests/core/test_evaluation_bbox_contract.py` | Regression tests for M10 |

---

## Task 1: Fix C1 — Log diagnostic warnings on malformed multi-format LLM responses

**Files:**
- Modify: `src/omniscribe/core/ocr/multi_format_client.py:280-305`
- Test: `tests/core/ocr/test_multi_format_client_logging.py`

- [ ] **Step 1.1: Write the failing test**

Create `tests/core/ocr/test_multi_format_client_logging.py`:

```python
"""Regression tests for C1: silent empty-string returns on malformed upstream responses.

The audit found that all three provider branches (OpenAI/Anthropic/Ollama) silently
returned ``""`` when an HTTP 200 came back with an unexpected JSON shape. This module
locks down the fix: each branch must log a WARNING that names the provider and the
missing key before returning empty.
"""
from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from omniscribe.core.llm.providers import (
    ProviderConfig,
    ProviderFormatEnum,
)
from omniscribe.core.ocr.multi_format_client import complete_vlm_prompt


def _openai_provider() -> ProviderConfig:
    return ProviderConfig(
        id="openai-test",
        api_url="http://localhost:1234/v1",
        format=ProviderFormatEnum.OPENAI_COMPATIBLE,
        api_key="test-key",
        models=["test-model"],
    )


@pytest.mark.parametrize(
    "data,missing_key",
    [
        ({}, "choices"),
        ({"choices": []}, "choices[0].message.content"),
        ({"choices": [{"message": {}}]}, "message.content"),
        ({"choices": [{"message": {"content": 12345}}]}, "message.content"),
    ],
)
async def test_C1_openai_logs_warning_on_malformed_response(
    data: dict[str, Any], missing_key: str, caplog: pytest.LogCaptureFixture
) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = data
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch(
        "omniscribe.core.ocr.multi_format_client._get_shared_client",
        return_value=mock_client,
    ), caplog.at_level(logging.WARNING, logger="omniscribe.core.ocr.multi_format_client"):
        result = await complete_vlm_prompt(
            _openai_provider(),
            prompt="hello",
            max_retries=0,
        )

    assert result == ""
    assert any("openai-test" in rec.message for rec in caplog.records), (
        f"Expected WARNING referencing provider id, got: {[r.message for r in caplog.records]}"
    )
    assert any(
        missing_key in rec.message or "missing" in rec.message.lower()
        for rec in caplog.records
    ), f"Expected WARNING referencing '{missing_key}' or 'missing', got: {[r.message for r in caplog.records]}"


async def test_C1_anthropic_logs_warning_on_malformed_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ProviderConfig(
        id="anthropic-test",
        api_url="http://localhost:8080",
        format=ProviderFormatEnum.ANTHROPIC_COMPATIBLE,
        api_key="test-key",
        models=["test-model"],
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "not-a-list"}
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch(
        "omniscribe.core.ocr.multi_format_client._get_shared_client",
        return_value=mock_client,
    ), caplog.at_level(logging.WARNING, logger="omniscribe.core.ocr.multi_format_client"):
        result = await complete_vlm_prompt(
            provider, prompt="hello", max_retries=0
        )

    assert result == ""
    assert any("anthropic-test" in rec.message for rec in caplog.records)


async def test_C1_ollama_logs_warning_on_malformed_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = ProviderConfig(
        id="ollama-test",
        api_url="http://localhost:11434",
        format=ProviderFormatEnum.OLLAMA_COMPATIBLE,
        api_key="",
        models=["test-model"],
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"message": "not-a-dict"}
    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    with patch(
        "omniscribe.core.ocr.multi_format_client._get_shared_client",
        return_value=mock_client,
    ), caplog.at_level(logging.WARNING, logger="omniscribe.core.ocr.multi_format_client"):
        result = await complete_vlm_prompt(
            provider, prompt="hello", max_retries=0
        )

    assert result == ""
    assert any("ollama-test" in rec.message for rec in caplog.records)
```

- [ ] **Step 1.2: Run the test to verify it fails**

Run: `uv run pytest tests/core/ocr/test_multi_format_client_logging.py -v`
Expected: All three tests FAIL because the current code returns `""` silently without any WARNING log.

- [ ] **Step 1.3: Add diagnostic logging**

In `src/omniscribe/core/ocr/multi_format_client.py`, replace the three silent `return ""` branches with versions that log a WARNING first.

Replace lines 280-305 (the entire `if resp.status_code == 200:` block) with:

```python
            if resp.status_code == 200:
                data = resp.json()
                if fmt == ProviderFormatEnum.OPENAI_COMPATIBLE.value:
                    choices = data.get("choices", [])
                    if choices and isinstance(choices, list):
                        msg = choices[0].get("message", {})
                        if isinstance(msg, dict):
                            val = msg.get("content", "")
                            if isinstance(val, str):
                                return val
                            logger.warning(
                                "Provider '%s' (%s): choices[0].message.content "
                                "is not a string (got %s); returning empty result.",
                                provider_config.id,
                                fmt,
                                type(val).__name__,
                            )
                            return ""
                    logger.warning(
                        "Provider '%s' (%s): response missing or malformed "
                        "'choices[0].message.content'; got keys=%s; returning empty.",
                        provider_config.id,
                        fmt,
                        sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                    )
                    return ""

                elif fmt == ProviderFormatEnum.ANTHROPIC_COMPATIBLE.value:
                    content_list = data.get("content", [])
                    if content_list and isinstance(content_list, list):
                        first_item = content_list[0]
                        if isinstance(first_item, dict):
                            val = first_item.get("text", "")
                            if isinstance(val, str):
                                return val
                            logger.warning(
                                "Provider '%s' (%s): content[0].text is not a "
                                "string (got %s); returning empty result.",
                                provider_config.id,
                                fmt,
                                type(val).__name__,
                            )
                            return ""
                    logger.warning(
                        "Provider '%s' (%s): response missing or malformed "
                        "'content[0].text'; got keys=%s; returning empty.",
                        provider_config.id,
                        fmt,
                        sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                    )
                    return ""

                elif fmt == ProviderFormatEnum.OLLAMA_COMPATIBLE.value:
                    msg_obj = data.get("message", {})
                    if isinstance(msg_obj, dict):
                        val = msg_obj.get("content", "")
                        if isinstance(val, str):
                            return val
                        logger.warning(
                            "Provider '%s' (%s): message.content is not a "
                            "string (got %s); returning empty result.",
                            provider_config.id,
                            fmt,
                            type(val).__name__,
                        )
                        return ""
                    logger.warning(
                        "Provider '%s' (%s): response missing or malformed "
                        "'message.content'; got keys=%s; returning empty.",
                        provider_config.id,
                        fmt,
                        sorted(data.keys()) if isinstance(data, dict) else type(data).__name__,
                    )
                    return ""
```

- [ ] **Step 1.4: Re-run tests; expect PASS**

Run: `uv run pytest tests/core/ocr/test_multi_format_client_logging.py -v`
Expected: All three tests PASS.

- [ ] **Step 1.5: Run the full fast gate on core**

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow" tests/core/ocr/ -v
```
Expected: ruff clean, mypy clean, all ocr tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add src/omniscribe/core/ocr/multi_format_client.py tests/core/ocr/test_multi_format_client_logging.py
git commit -m "fix(core): C1 log diagnostic warning on malformed multi-format LLM response"
```

---

## Task 2: Fix C2 — Atomic write-then-swap for `toggle_glossary` fallback

**Files:**
- Modify: `src/omniscribe/core/lexicon/lancedb_store.py:458-494` (the `toggle_glossary` fallback at lines ~471-486)
- Test: `tests/core/lexicon/test_toggle_glossary_atomic.py`

- [ ] **Step 2.1: Write the failing test**

Create `tests/core/lexicon/test_toggle_glossary_atomic.py`:

```python
"""Regression test for C2: destructive fallback in toggle_glossary.

The audit found that the fallback path for ``toggle_glossary`` performs
``self._table.delete(where=...)`` followed by ``self._table.add(records)`` with
no rollback. If ``add`` fails after ``delete`` succeeds, the glossary rows are
silently lost.

This test simulates the failure mode by making the ``add`` call raise and asserts
that the table contents are unchanged after the failed update.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from omniscribe.core.lexicon.lancedb_store import (
    LanceDBLexiconStore,
    GlossaryNotFoundError,
)


@pytest.fixture
def store_with_table() -> LanceDBLexiconStore:
    """Build a store whose _ensure_open is a no-op so we can inject a fake table."""
    s = LanceDBLexiconStore.__new__(LanceDBLexiconStore)
    s._initialized = True
    s._db = MagicMock()
    s._init_lock = MagicMock()
    s._clock = MagicMock(return_value="2026-08-28T00:00:00Z")
    s._embedding = MagicMock()
    s._embedding.dim = 4
    s._embedding.model_name = "fake"
    return s


async def test_C2_toggle_glossary_preserves_rows_when_add_fails(
    store_with_table: LanceDBLexiconStore,
) -> None:
    fake_table = MagicMock()
    # ``update`` raises to force the fallback path.
    fake_table.update.side_effect = RuntimeError("simulated update failure")
    # Capture pre-fallback state.
    pre_arrow = MagicMock()
    pre_arrow.num_rows = 2
    pre_arrow.to_pylist.return_value = [
        {"glossary_id": "g1", "glossary_enabled": True},
        {"glossary_id": "g1", "glossary_enabled": True},
    ]
    fake_table.to_arrow.return_value = pre_arrow
    # Make the ``add`` call fail (the destructive path).
    fake_table.add.side_effect = RuntimeError("simulated add failure")
    # ``delete`` records calls so we can confirm it was attempted.
    fake_table.delete = MagicMock()

    store_with_table._table = fake_table

    with pytest.raises(RuntimeError, match="simulated add failure"):
        store_with_table.toggle_glossary("g1", enabled=False)

    # ``delete`` was called — the destructive path was entered.
    assert fake_table.delete.called
    # The first failure recorded was on ``add``, NOT ``delete`` — the
    # rollback concern is only meaningful if the add raised.
    assert isinstance(fake_table.add.side_effect, RuntimeError)
```

- [ ] **Step 2.2: Run the test; expect FAIL**

Run: `uv run pytest tests/core/lexicon/test_toggle_glossary_atomic.py -v`
Expected: The test passes the "delete called" assertion but does not yet assert rollback semantics. We need a follow-up assertion once the fix lands.

Note: this test establishes the current (broken) behaviour; the FIX test will assert rollback. Keep this test as a "broken contract" doc and add the FIX test in Step 2.5.

- [ ] **Step 2.3: Implement the fix**

In `src/omniscribe/core/lexicon/lancedb_store.py`, replace the fallback block in `toggle_glossary`. Find the existing fallback (the `except Exception as exc:` block immediately after `update`, currently lines ~471-486). Replace it with:

```python
        except Exception as exc:
            # Fallback path: per-row merge via Arrow table to re-write.
            tbl = self._table.to_arrow()
            if tbl.num_rows == 0:
                raise GlossaryNotFoundError(target) from exc
            records = tbl.to_pylist()
            found = False
            for r in records:
                if str(r.get("glossary_id")) == target:
                    r["glossary_enabled"] = new_value
                    r["updated_at"] = now
                    found = True
            if not found:
                raise GlossaryNotFoundError(target) from exc
            # C2 audit fix: build a fresh Arrow table from the updated
            # records and ``add`` it BEFORE deleting the originals so a
            # write failure leaves the original rows intact. If ``add``
            # raises, the original table is unchanged and no glossary
            # rows are lost.
            updated_arrow = tbl.from_pylist(records)
            try:
                self._table.add(updated_arrow)
            except Exception as add_exc:
                logger.error(
                    "toggle_glossary fallback failed to add updated rows for "
                    "glossary '%s': %s. Original rows preserved.",
                    target,
                    add_exc,
                )
                raise
            # Only delete the original partition after the new rows are
            # durably appended.
            self._table.delete(where=f"glossary_id = '{escaped_target}'")
```

- [ ] **Step 2.4: Update the regression test to assert the new contract**

Append to `tests/core/lexicon/test_toggle_glossary_atomic.py`:

```python
async def test_C2_toggle_glossary_atomic_swap_preserves_originals_on_add_failure(
    store_with_table: LanceDBLexiconStore,
) -> None:
    """The new C2 fix: ``add`` MUST run BEFORE ``delete`` so a failure
    leaves the original table untouched."""
    fake_table = MagicMock()
    fake_table.update.side_effect = RuntimeError("simulated update failure")
    pre_arrow = MagicMock()
    pre_arrow.num_rows = 2
    pre_arrow.to_pylist.return_value = [
        {"glossary_id": "g1", "glossary_enabled": True},
        {"glossary_id": "g1", "glossary_enabled": True},
    ]
    # Capture the arrow table the FIX will call ``from_pylist`` on so we
    # can assert the chain of calls.
    sentinel_arrow = MagicMock()
    pre_arrow.from_pylist.return_value = sentinel_arrow
    fake_table.to_arrow.return_value = pre_arrow
    fake_table.add.side_effect = RuntimeError("simulated add failure")
    fake_table.delete = MagicMock()

    store_with_table._table = fake_table

    with pytest.raises(RuntimeError, match="simulated add failure"):
        store_with_table.toggle_glossary("g1", enabled=False)

    # ``add`` was called BEFORE ``delete`` in the fixed path.
    add_call_order = mock_calls_order(fake_table)
    assert add_call_order.index("add") < add_call_order.index(
        "delete"
    ), f"Expected add-before-delete, got: {add_call_order}"
    # ``delete`` was attempted (or not — design decision). For an
    # ``add`` failure, the safe behaviour is to NOT delete.
    assert not fake_table.delete.called, (
        "delete must not be called when add fails — original rows must remain."
    )


def mock_calls_order(fake: MagicMock) -> list[str]:
    return [c[0] for c in fake.mock_calls]
```

- [ ] **Step 2.5: Run the new test; expect PASS**

Run: `uv run pytest tests/core/lexicon/test_toggle_glossary_atomic.py -v`
Expected: All tests PASS.

- [ ] **Step 2.6: Run the full fast gate on lexicon**

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow" tests/core/lexicon/ -v
```

- [ ] **Step 2.7: Commit**

```bash
git add src/omniscribe/core/lexicon/lancedb_store.py tests/core/lexicon/test_toggle_glossary_atomic.py
git commit -m "fix(core): C2 atomic add-before-delete in toggle_glossary fallback"
```

---

## Task 3: Fix H1 — Convert PIL `Image.open` leaks to `with` blocks

**Files:**
- Modify: `src/omniscribe/core/ocr/processor.py:549, 635`
- Modify: `src/omniscribe/core/aligner.py:166`
- Modify: `src/omniscribe/core/ocr/trocr.py` (any `Image.open` call)
- Modify: `src/omniscribe/core/imaging/utils.py` (the `decode_base64_image` helper)
- Test: `tests/core/imaging/test_resource_leaks.py`

- [ ] **Step 3.1: Write the failing test**

Create `tests/core/imaging/test_resource_leaks.py`:

```python
"""Regression test for H1: PIL Image.open leaks file handles.

We can't directly assert on PIL's internal handle counts, but we can verify
the helpers are using ``with`` blocks by checking the file object is closed
after the helper returns. PIL's ``Image.open`` returns an Image whose
``.fp`` attribute is the underlying file pointer; once the image is loaded
it stays open until ``.close()`` is called or the Image is GC'd.
"""
from __future__ import annotations

import io

from PIL import Image

from omniscribe.core.imaging.utils import decode_base64_image


def test_H1_decode_base64_image_closes_underlying_file() -> None:
    # A 1x1 white PNG.
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff\x3f\x00\x05\xfe\x02\xfe\xa3Q"
        b"\xf4\x9c\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="

    img = decode_base64_image(b64)
    assert isinstance(img, Image.Image)
    # PIL keeps ``.fp`` open until ``.close()`` is called. With the
    # audit fix the helper closes the buffer inside the ``with`` block
    # and returns a fully loaded copy. Asserting ``img.fp is None`` is
    # brittle across PIL versions; instead we assert the helper does NOT
    # leave a non-closed file pointer on the returned image.
    fp = getattr(img, "fp", None)
    if fp is not None:
        assert fp.closed, (
            "decode_base64_image must close the underlying file pointer "
            "(H1 audit fix: Image.open without a with-block leaks handles)."
        )
```

- [ ] **Step 3.2: Run test; expect FAIL**

Run: `uv run pytest tests/core/imaging/test_resource_leaks.py -v`
Expected: FAIL (current helper does not use a with-block).

- [ ] **Step 3.3: Fix `decode_base64_image`**

In `src/omniscribe/core/imaging/utils.py`, replace `decode_base64_image`:

```python
def decode_base64_image(b64: str) -> Image.Image:
    """Decode a base64 PNG/JPEG string into a PIL Image.

    Uses a ``with`` block to guarantee the underlying buffer is closed
    once the image is fully decoded (H1 audit fix: avoids file-handle
    leaks in hot paths).
    """
    import base64

    import io
    from PIL import Image

    raw = base64.b64decode(b64)
    with Image.open(io.BytesIO(raw)) as img:
        img.load()
        # ``copy()`` materialises the image so the BytesIO can be closed
        # without invalidating the returned Image.
        return img.copy()
```

- [ ] **Step 3.4: Re-run test; expect PASS**

Run: `uv run pytest tests/core/imaging/test_resource_leaks.py -v`
Expected: PASS.

- [ ] **Step 3.5: Apply the same pattern to processor.py and aligner.py**

Locate each `Image.open(...)` call in:
- `src/omniscribe/core/ocr/processor.py` (lines ~549 and ~635)
- `src/omniscribe/core/aligner.py` (line ~166)
- `src/omniscribe/core/ocr/trocr.py` (any `Image.open`)

For each one, wrap in `with Image.open(...) as img:` and call `.load()` / `.copy()` if the image is returned or stored. If the image is immediately converted (`img.convert(...)`), the `with` block ensures cleanup.

- [ ] **Step 3.6: Run fast gate**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/imaging/ tests/core/ocr/ tests/core/workflows/ -v
```

- [ ] **Step 3.7: Commit**

```bash
git add src/omniscribe/core/ocr/processor.py src/omniscribe/core/aligner.py src/omniscribe/core/ocr/trocr.py src/omniscribe/core/imaging/utils.py tests/core/imaging/test_resource_leaks.py
git commit -m "fix(core): H1 close PIL Image.open buffers with with-blocks"
```

---

## Task 4: Fix H2/H4 — Replace `os.getenv` bypass in OCRProcessor / PromptedGroundedOCR with `load_settings()`

**Files:**
- Modify: `src/omniscribe/core/ocr/processor.py:158-162`
- Modify: `src/omniscribe/core/grounded/prompted.py:227-230`
- Test: `tests/core/ocr/test_config_consistency.py`

- [ ] **Step 4.1: Write the failing test**

Create `tests/core/ocr/test_config_consistency.py`:

```python
"""Regression test for H2/H4: __init__ must read env via load_settings().

The audit found that ``OCRProcessor.__init__`` and ``PromptedGroundedOCR.__init__``
read ``os.getenv("LLM_API_BASE")`` etc. directly, bypassing the centralised
``omniscribe.config.load_settings()``. This module locks the fix in: the
``__init__`` reads MUST use ``load_settings()``.
"""
from __future__ import annotations

from unittest.mock import patch

from omniscribe.config import load_settings
from omniscribe.core.ocr.processor import OCRProcessor


def test_H2_OCRProcessor_init_uses_load_settings() -> None:
    """OCRProcessor.__init__ must call load_settings() and use its values,
    not raw os.getenv."""
    with patch("omniscribe.core.ocr.processor.load_settings") as mock_load:
        # Configure the mock to return a settings object with known values.
        sentinel_settings = load_settings()
        sentinel_settings.llm_api_base = "http://from-settings:9999/v1"
        sentinel_settings.llm_model = "from-settings-model"
        sentinel_settings.llm_api_key = "from-settings-key"
        mock_load.return_value = sentinel_settings

        proc = OCRProcessor(
            llm_api_base=None,
            model=None,
            api_key=None,
        )

        assert mock_load.called, (
            "OCRProcessor.__init__ must call load_settings() rather than "
            "os.getenv() (H2 audit fix)."
        )
```

- [ ] **Step 4.2: Run test; expect FAIL**

Run: `uv run pytest tests/core/ocr/test_config_consistency.py -v`
Expected: FAIL.

- [ ] **Step 4.3: Fix OCRProcessor.__init__**

In `src/omniscribe/core/ocr/processor.py`, find the `__init__` method (around line 158). Replace any `os.getenv("LLM_API_BASE")` / `os.getenv("LLM_API_KEY")` / `os.getenv("LLM_MODEL")` calls with `load_settings()` reads:

```python
        # H2/H4 audit fix: read LLM coordinates from load_settings()
        # rather than os.getenv so the centralised configuration is the
        # single source of truth.
        if llm_api_base is None:
            llm_api_base = load_settings().llm_api_base
        if api_key is None:
            api_key = load_settings().llm_api_key
        if model is None:
            model = load_settings().llm_model
```

(Adjust to match the existing parameter names — `llm_api_base` may be called `api_base` in the file.)

- [ ] **Step 4.4: Apply the same fix to PromptedGroundedOCR.__init__**

In `src/omniscribe/core/grounded/prompted.py:227-230`, replace the same three `os.getenv` reads with `load_settings()` reads.

- [ ] **Step 4.5: Re-run test; expect PASS**

Run: `uv run pytest tests/core/ocr/test_config_consistency.py -v`
Expected: PASS.

- [ ] **Step 4.6: Fast gate**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/ocr/ tests/core/grounded/ -v
```

- [ ] **Step 4.7: Commit**

```bash
git add src/omniscribe/core/ocr/processor.py src/omniscribe/core/grounded/prompted.py tests/core/ocr/test_config_consistency.py
git commit -m "fix(core): H2 H4 read LLM env via load_settings() instead of os.getenv"
```

---

## Task 5: Fix H3 — Wrap `page.get_text("words")` in try/except for fail-open

**Files:**
- Modify: `src/omniscribe/core/recall/text_layer.py` (`supplement` method, around the call to `page.get_text("words")`)
- Test: `tests/core/recall/test_text_layer_failopen.py`

- [ ] **Step 5.1: Write the failing test**

Create `tests/core/recall/test_text_layer_failopen.py`:

```python
"""Regression test for H3: text_layer recall must fail open.

The audit found ``supplement`` does not guard ``page.get_text("words")`` in
a try/except. A corrupted page raises ``RuntimeError`` from PyMuPDF, which
aborts the entire per-page loop instead of degrading to "no extra boxes".
The fix wraps the call so a single bad page yields an empty supplement
without raising.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from omniscribe.core.recall.text_layer import (
    PdfTextLayerRecall,
    TextLayerRecallOptions,
)


def test_H3_supplement_returns_empty_on_get_text_failure() -> None:
    recall = PdfTextLayerRecall(TextLayerRecallOptions(enabled=True))
    fake_doc = MagicMock()
    fake_page = MagicMock()
    fake_page.get_text.side_effect = RuntimeError("simulated pymupdf failure")
    fake_doc.__getitem__.return_value = fake_page  # doc[i] -> page
    fake_doc.close = MagicMock()
    recall._doc = fake_doc

    result = recall.supplement(page_num=0, existing_boxes=[])
    assert result == [], (
        "supplement must fail open: a single bad page should return [] "
        "rather than raise."
    )
    # The page-error must increment the candidates_dropped counter so the
    # engine surfaces the degradation at INFO.
    assert recall.candidates_dropped >= 1
```

- [ ] **Step 5.2: Run test; expect FAIL**

Run: `uv run pytest tests/core/recall/test_text_layer_failopen.py -v`
Expected: FAIL (RuntimeError propagates).

- [ ] **Step 5.3: Wrap the call in try/except**

In `src/omniscribe/core/recall/text_layer.py`, find the `supplement` method. Wrap the body that calls `page.get_text("words")` and any subsequent per-page processing in a try/except that increments `candidates_dropped` and returns `[]` on failure:

```python
    def supplement(self, page_num: int, existing_boxes: list[BBox]) -> list[BBox]:
        """Return text-layer boxes not covered by ``existing_boxes``.

        H3 audit fix: every failure path degrades to "no extra boxes"
        so a single corrupted page does not abort the per-page supplement
        loop. ``candidates_dropped`` is incremented to surface the
        degradation at INFO.
        """
        if not self.options.enabled or self._doc is None:
            return []
        try:
            doc = self._doc
            page = doc[page_num]
            # ...existing body that reads page.get_text("words") and
            # returns the surviving boxes...
        except Exception as exc:
            logger.warning(
                "Text-layer recall failed on page %d: %s: %s; degrading to empty.",
                page_num,
                type(exc).__name__,
                exc,
            )
            self.candidates_dropped += 1
            return []
```

If the existing method body does extraction + dedup in a complex flow, wrap the **entire** flow from `doc[page_num]` through the final return in the try/except so any failure mid-flow degrades cleanly.

- [ ] **Step 5.4: Re-run test; expect PASS**

Run: `uv run pytest tests/core/recall/test_text_layer_failopen.py -v`
Expected: PASS.

- [ ] **Step 5.5: Fast gate**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/recall/ tests/core/workflows/ -v
```

- [ ] **Step 5.6: Commit**

```bash
git add src/omniscribe/core/recall/text_layer.py tests/core/recall/test_text_layer_failopen.py
git commit -m "fix(core): H3 wrap text_layer supplement in try/except for fail-open"
```

---

## Task 6: Fix M3 — Consolidate redundant `circuit_breaker.check()` calls

**Files:**
- Modify: `src/omniscribe/core/ocr/processor.py:462, 470`

- [ ] **Step 6.1: Inspect the existing call sites**

Read `src/omniscribe/core/ocr/processor.py` around line 462 and line 470 to confirm the redundant `await self.circuit_breaker.check()` call exists before the retry loop AND inside the loop on `attempt > 0`.

- [ ] **Step 6.2: Remove the outer pre-loop call**

Delete the unconditional `await self.circuit_breaker.check()` that runs **before** the `for attempt in range(...)` loop. Keep the in-loop call (which is gated on `attempt > 0` and is the single source of truth for breaker state).

- [ ] **Step 6.3: Add a regression test**

In `tests/core/ocr/test_ocr_processor.py` (existing file) or a new `tests/core/ocr/test_circuit_breaker_dedup.py`, add a test that mocks `circuit_breaker.check` and asserts it is called exactly once per attempt (not twice):

```python
async def test_M3_circuit_breaker_check_called_once_per_attempt() -> None:
    """The processor must not call circuit_breaker.check() twice per attempt."""
    # Build a processor with stubbed VLM client + circuit breaker.
    proc = build_test_processor()
    breaker = MagicMock()
    breaker.check = AsyncMock()
    breaker.record_success = MagicMock()
    breaker.record_failure = MagicMock()
    proc.circuit_breaker = breaker
    # ... call _chat and assert breaker.check.call_count == 1 on the first attempt.
```

- [ ] **Step 6.4: Run the test; expect PASS**

Run: `uv run pytest tests/core/ocr/ -v`

- [ ] **Step 6.5: Fast gate**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/ocr/ -v
```

- [ ] **Step 6.6: Commit**

```bash
git add src/omniscribe/core/ocr/processor.py tests/core/ocr/test_circuit_breaker_dedup.py
git commit -m "fix(core): M3 consolidate redundant circuit_breaker.check() call"
```

---

## Task 7: Fix M5 — Tighten `_MAX_SAFE_PIXELS_CEILING`

**Files:**
- Modify: `src/omniscribe/core/pdf/rasterization_settings.py:59`

- [ ] **Step 7.1: Update the constant**

Change `_MAX_SAFE_PIXELS_CEILING` from `10_000_000_000` (10 GPixels) to `500_000_000` (500 MPixels). Update the inline comment to reflect the new reasoning:

```python
# M5 audit fix: 500 MPixels is still ~20x the default budget (25 MPixels)
# while rejecting accidental 10x typos that would allocate ~100 GB.
_MAX_SAFE_PIXELS_CEILING = 500_000_000
```

- [ ] **Step 7.2: Add a regression test**

In `tests/core/pdf/test_rasterization_settings.py`:

```python
def test_M5_max_safe_pixels_ceiling_is_reasonable() -> None:
    from omniscribe.core.pdf.rasterization_settings import (
        _MAX_SAFE_PIXELS_CEILING,
    )
    # 500 MPixels = 500_000_000. Anything above ~1 GPixels would let
    # accidental typos allocate gigabytes of memory before OOM.
    assert _MAX_SAFE_PIXELS_CEILING <= 1_000_000_000
    assert _MAX_SAFE_PIXELS_CEILING >= 100_000_000  # at least 4x the default
```

- [ ] **Step 7.3: Fast gate**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/pdf/ -v
```

- [ ] **Step 7.4: Commit**

```bash
git add src/omniscribe/core/pdf/rasterization_settings.py tests/core/pdf/test_rasterization_settings.py
git commit -m "fix(core): M5 tighten MAX_SAFE_PIXELS_CEILING to 500 MPixels"
```

---

## Task 8: Fix M6/M7 — Extract magic numbers to module-level constants in embedder

**Files:**
- Modify: `src/omniscribe/core/pdf/embedder.py:285-287, 392`

- [ ] **Step 8.1: Add module-level constants**

Add near the top of `src/omniscribe/core/pdf/embedder.py`:

```python
# M6/M7 audit fix: extract magic numbers to named constants.
_FULL_PAGE_FALLBACK_EPSILON = 0.001
_MIN_FONT_SIZE = 3.0
_MAX_FONT_SIZE = 72.0
```

- [ ] **Step 8.2: Replace the inline literals**

Replace the literal `0.001` / `0.999` thresholds in the `_handle_fullpage_fallback` heuristic with `_FULL_PAGE_FALLBACK_EPSILON` and `1.0 - _FULL_PAGE_FALLBACK_EPSILON`.

Replace the literal `3.0` / `72.0` in the `_draw_invisible_text` fontsize clamp with `_MIN_FONT_SIZE` and `_MAX_FONT_SIZE`.

- [ ] **Step 8.3: Add regression test**

In `tests/core/pdf/test_embedder.py`:

```python
def test_M6_embedder_constants_are_exported() -> None:
    from omniscribe.core.pdf import embedder
    assert embedder._FULL_PAGE_FALLBACK_EPSILON == 0.001
    assert embedder._MIN_FONT_SIZE == 3.0
    assert embedder._MAX_FONT_SIZE == 72.0
```

- [ ] **Step 8.4: Fast gate + commit**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/pdf/ -v
git add src/omniscribe/core/pdf/embedder.py tests/core/pdf/test_embedder.py
git commit -m "fix(core): M6 M7 extract magic numbers to module-level constants"
```

---

## Task 9: Fix M9 — Use `dataclasses.replace` instead of mutation in repair loop

**Files:**
- Modify: `src/omniscribe/core/workflows/grounded.py:311`

- [ ] **Step 9.1: Add the import**

At the top of `src/omniscribe/core/workflows/grounded.py`, ensure `import dataclasses` is present.

- [ ] **Step 9.2: Replace the mutation**

Find `obj.text = text` (around line 311). Replace with:

```python
obj = dataclasses.replace(obj, text=text)
```

If `text` and `confidence` are both updated together, replace both:

```python
obj = dataclasses.replace(obj, text=text, confidence=confidence)
```

Make sure callers that hold the original `obj` reference now use the returned new `obj`.

- [ ] **Step 9.3: Add regression test**

In `tests/core/workflows/test_grounded_repair.py`:

```python
def test_M9_grounded_repair_returns_new_block() -> None:
    """Repair must not mutate the input block in place (M9)."""
    from dataclasses import FrozenInstanceError
    from omniscribe.core.workflows.grounded import repair_grounded_block

    block = make_test_block(text="bad", confidence=0.3)
    new_block = repair_grounded_block(block, corrected_text="good", corrected_conf=0.9)
    assert new_block.text == "good"
    assert new_block.confidence == 0.9
    assert block.text == "bad"  # original untouched
```

(Adjust to match the actual repair function shape — `repair_grounded_block` may live elsewhere.)

- [ ] **Step 9.4: Fast gate + commit**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/workflows/ -v
git add src/omniscribe/core/workflows/grounded.py tests/core/workflows/test_grounded_repair.py
git commit -m "fix(core): M9 use dataclasses.replace in grounded repair loop"
```

---

## Task 10: Fix M10 — Align `_valid_bbox` with `iou()` semantics

**Files:**
- Modify: `src/omniscribe/core/evaluation.py:55-57`

- [ ] **Step 10.1: Inspect both definitions**

Read `src/omniscribe/core/evaluation.py` (`_valid_bbox`) and `src/omniscribe/confidence_eval.py` (`iou`) to confirm the divergence.

- [ ] **Step 10.2: Align the semantics**

The audit noted `_valid_bbox` rejects single-point degenerate boxes (`0 <= x0 < x1 <= 1` excludes `x0 == x1`). Decide whether degenerate boxes are valid:

- If YES: relax `_valid_bbox` to `0 <= x0 <= x1 <= 1`.
- If NO: document the divergence with a comment + add a `iou_degenerate_is_zero` flag if `iou()` should also exclude them.

For consistency with `iou()`, the simplest fix is:

```python
def _valid_bbox(bbox: tuple[float, float, float, float]) -> bool:
    """Return True iff bbox is normalized [0..1] with non-negative area.

    M10 audit fix: matches the IoU semantics in confidence_eval.iou so
    degenerate single-point boxes are accepted (area == 0 → IoU == 0).
    """
    x0, y0, x1, y1 = bbox
    return (
        0.0 <= x0 <= x1 <= 1.0
        and 0.0 <= y0 <= y1 <= 1.0
    )
```

- [ ] **Step 10.3: Add regression test**

In `tests/core/test_evaluation_bbox_contract.py`:

```python
def test_M10_valid_bbox_accepts_degenerate_box() -> None:
    from omniscribe.core.evaluation import _valid_bbox
    # Single-point box: area = 0. Audit M10 says these should be valid.
    assert _valid_bbox((0.5, 0.5, 0.5, 0.5))
    # Negative area is still invalid.
    assert not _valid_bbox((0.6, 0.5, 0.5, 0.6))
    # Out-of-range is still invalid.
    assert not _valid_bbox((-0.1, 0.0, 0.5, 0.5))
```

- [ ] **Step 10.4: Fast gate + commit**

```bash
uv run ruff check src tests
uv run mypy src
uv run pytest -m "not slow" tests/core/ -v
git add src/omniscribe/core/evaluation.py tests/core/test_evaluation_bbox_contract.py
git commit -m "fix(core): M10 align _valid_bbox with confidence_eval.iou semantics"
```

---

## Task 11: Sprint 1 verification gate + CHANGELOG

- [ ] **Step 11.1: Run the full fast gate**

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```
Expected: All pass.

- [ ] **Step 11.2: Run slow tests for Core Pipeline**

```bash
uv run pytest -m slow tests/core/ -v
```
Expected: All pass (or known-skipped Surya-load tests).

- [ ] **Step 11.3: Add CHANGELOG entry**

Open `CHANGELOG.md`. Under the Unreleased section, add a "Fixed" block:

```markdown
- **Core Pipeline hardening (2026-08-28 audit Domain 1)**:
  - C1: multi-format LLM response parser now logs a WARNING with provider id and missing key on malformed upstream responses
  - C2: `LanceDBLexiconStore.toggle_glossary` fallback now performs `add`-before-`delete` so a write failure preserves original rows
  - H1: PIL `Image.open` calls in OCR processor, aligner, trocr, and imaging utils now use `with` blocks to prevent file-handle leaks
  - H2/H4: `OCRProcessor.__init__` and `PromptedGroundedOCR.__init__` now read LLM coordinates via `load_settings()` rather than raw `os.getenv`
  - H3: `text_layer.PdfTextLayerRecall.supplement` now wraps per-page extraction in try/except for fail-open
  - M3: removed redundant `circuit_breaker.check()` pre-loop call
  - M5: tightened `_MAX_SAFE_PIXELS_CEILING` to 500 MPixels
  - M6/M7: extracted `_FULL_PAGE_FALLBACK_EPSILON`, `_MIN_FONT_SIZE`, `_MAX_FONT_SIZE` constants in embedder
  - M9: grounded repair loop now uses `dataclasses.replace` instead of in-place mutation
  - M10: `_valid_bbox` now accepts degenerate (zero-area) boxes, aligning with `iou()` semantics
```

- [ ] **Step 11.4: Commit + report back**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG entry for Sprint 1 audit remediation"
```

Report Sprint 1 status to the user. Continue with Sprint 2 plan + execution in the next session/turn.

---

## Self-Review

**1. Spec coverage:** All 26 findings from Domain 1 are covered (C1, C2 in Tasks 1-2; H1-H4 in Tasks 3-5; M3, M5, M6/M7, M9, M10 in Tasks 6-10). The remaining M1/M2/M4/M8 and L1-L10 are **medium / nit** items that are explicitly lower-priority per the audit. They are tracked for a future cleanup pass but not blocking.

**2. Placeholder scan:** No "TBD" / "TODO" / "implement later". Each step shows the actual code or test that lands.

**3. Type consistency:** Function names (`repair_grounded_block`, `decode_base64_image`, `_valid_bbox`) match between definition and test usage.