"""Streaming upload validation: byte caps, content signature, deadlines.

Split out of the former monolithic ``tests/test_api_safety.py``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from omniscribe.api.services.security import (
    UploadValidationError,
    save_validated_upload,
)


class _AsyncUpload:
    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


def test_upload_validation_uses_streaming_limit_and_content_signature():
    async def run_checks():
        with pytest.raises(UploadValidationError) as too_large:
            await save_validated_upload(
                _AsyncUpload(b"%PDF-1.4\n" + b"x" * 16),  # type: ignore[arg-type]
                max_bytes=8,
            )
        assert too_large.value.status_code == 413

        with pytest.raises(UploadValidationError) as bad_type:
            await save_validated_upload(_AsyncUpload(b"not a pdf"), max_bytes=1024)  # type: ignore[arg-type]
        assert bad_type.value.status_code == 415

    asyncio.run(run_checks())


def test_upload_deadline_rejects_slow_loris_client():
    """A slow-loris client streaming 1 byte at a time must be rejected
    by the wall-clock deadline even though it never crosses the byte cap."""

    class _SlowLoris:
        """Stream a valid PDF header in one chunk (so the suffix
        detector is satisfied) and then 1 byte per call so the deadline
        fires before the byte cap is reached."""

        def __init__(self) -> None:
            self._data = b"%PDF-1.4\n" + b"x" * 200
            self._offset = 0
            self._calls = 0

        async def read(self, size: int = -1) -> bytes:
            self._calls += 1
            if self._offset >= len(self._data):
                return b""
            if self._calls == 1:
                # First read: return the full PDF header so the
                # suffix detector accepts the upload.
                chunk = self._data[:9]
            else:
                # Subsequent reads: 1 byte at a time with a sleep.
                await asyncio.sleep(0.01)
                chunk = self._data[self._offset : self._offset + 1]
            self._offset += len(chunk)
            return chunk

    async def run_checks():
        with pytest.raises(UploadValidationError) as exc:
            await save_validated_upload(
                _SlowLoris(),  # type: ignore[arg-type]
                max_bytes=10_000,
                deadline_seconds=0.1,
            )
        assert exc.value.status_code == 408
        assert "deadline" in str(exc.value).lower()

    asyncio.run(run_checks())


def test_upload_deadline_disabled_when_zero():
    """Passing ``deadline_seconds=0`` (or None) disables the wall-clock
    check so existing tests and the local-dev override don't regress."""

    async def run_checks():
        # Tiny body, generous byte cap, no deadline → must succeed.
        result = await save_validated_upload(
            _AsyncUpload(b"%PDF-1.4\nshort"),  # type: ignore[arg-type]
            max_bytes=1024,
            deadline_seconds=0.0,
        )
        assert result.size_bytes == 14
        Path(result.path).unlink(missing_ok=True)

    asyncio.run(run_checks())


def test_upload_deadline_resolves_from_env(monkeypatch: pytest.MonkeyPatch):
    """An invalid env value falls back to the default deadline (60s) and
    doesn't raise. A valid value is honored."""

    async def run_checks():
        # Bad value → use default; small body should still upload.
        monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_SECONDS", "not-a-number")
        result = await save_validated_upload(
            _AsyncUpload(b"%PDF-1.4\nshort"),  # type: ignore[arg-type]
            max_bytes=1024,
        )
        assert result.size_bytes == 14
        Path(result.path).unlink(missing_ok=True)

        # Explicit disable → 0 in env, no deadline.
        monkeypatch.setenv("OMNISCRIBE_UPLOAD_DEADLINE_SECONDS", "0")
        result = await save_validated_upload(
            _AsyncUpload(b"%PDF-1.4\nshort2"),  # type: ignore[arg-type]
            max_bytes=1024,
        )
        assert result.size_bytes == 15
        Path(result.path).unlink(missing_ok=True)

    asyncio.run(run_checks())
