"""Regression test for H1: PIL Image.open leaks file handles.

The audit found multiple hot paths where ``Image.open(...)`` is called WITHOUT
a ``with`` block. PIL keeps the underlying file pointer open until the image is
explicitly closed or GC'd; on a long OCR run (200+ pages × per-page box OCR)
this can manifest as ``OSError: Too many open files`` mid-run.

The fix wraps each call in a ``with`` block (or explicitly closes the image).
This module verifies the canonical helper ``decode_base64_image`` uses a
``with`` block by inspecting its source code. The pattern is structural
(``with Image.open(...) as img:``) rather than behavioural because PIL's
internal lifecycle masks the leak for some call patterns, which makes a
behavioural test unreliable.
"""

from __future__ import annotations

import inspect
import re

from PIL import Image

from omniscribe.core.imaging import utils as imaging_utils


def test_H1_decode_base64_image_returns_image() -> None:
    """Sanity check: the helper still returns a usable PIL Image."""
    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    img = imaging_utils.decode_base64_image(b64)
    assert isinstance(img, Image.Image)
    assert img.size == (1, 1)
    # We don't pin the mode because PIL stores the actual source mode;
    # the helper preserves the original colorspace (RGB conversion was the
    # OLD behaviour that the audit said leaks; we now copy as-is).


def test_H1_decode_base64_image_uses_with_block() -> None:
    """H1 audit fix: ``decode_base64_image`` MUST use ``with Image.open(...)``.

    Structural test (regex on source) so the test is independent of PIL
    internals. PIL's Image lifecycle happens to close BytesIO buffers during
    ``.convert()`` for some call patterns, which makes a behavioural test
    unreliable. The ``with`` block makes cleanup intent explicit and
    protects against future refactors.
    """
    src = inspect.getsource(imaging_utils.decode_base64_image)
    # Match ``with Image.open(`` or ``with _PIL.Image.open(`` patterns.
    # The audit's fix uses ``with Image.open(io.BytesIO(...)) as img:``.
    assert re.search(r"with\s+Image\.open\s*\(", src), (
        "H1 regression: decode_base64_image does not use a `with Image.open(...)` "
        "block. The audit recommended wrapping Image.open in a with-block to "
        "guarantee cleanup of the underlying buffer/file pointer.\n\n"
        f"Source:\n{src}"
    )


def test_H1_decode_base64_image_call_does_not_throw() -> None:
    """The decoded image can be used after the helper returns."""
    import warnings

    b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
        "YAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        img = imaging_utils.decode_base64_image(b64)
        _ = img.tobytes()
