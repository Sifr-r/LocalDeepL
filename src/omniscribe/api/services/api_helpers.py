"""Cross-router API helper functions.

Lives in ``api/services/`` (not ``api/routers/``) because the helpers
themselves have no router context — they're called by multiple routers
and don't touch the FastAPI dependency tree.

History: the helpers used to live in ``api/routers/common.py`` and
exposed underscore-prefixed names (``_cleanup``,
``_stable_server_error``). Renaming them to public names and moving
them to a services module keeps the import surface honest (callers
should not need to know which router siblings a helper lives next to)
and makes the helpers easier to test in isolation.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from omniscribe.api.services.envelope import envelope_error
from omniscribe.api.services.security import (
    SERVER_ERROR_MESSAGE,
    cleanup_files,
)


def cleanup_files_dispatcher(*paths: str | None) -> None:
    """Delete each path if it exists; tolerate ``None`` and missing files.

    Thin wrapper over :func:`omniscribe.api.services.security.cleanup_files`
    kept as a named entry point so the routers don't need to import the
    security module directly for the common ``finally: cleanup_files(...)``
    pattern. Equivalent to the previous ``_cleanup`` in
    ``api/routers/common.py``.
    """
    cleanup_files(*paths)


def stable_server_error(status_code: int = 500) -> JSONResponse:
    """Return a stable error envelope for unexpected failures.

    The message is intentionally generic (it is the same one for every
    internal failure) so we don't leak implementation details to
    clients. Status code is configurable so the same envelope works
    for both 500 and 503, but the wording stays opaque.

    Equivalent to the previous ``_stable_server_error`` in
    ``api/routers/common.py``.
    """
    return envelope_error(
        status_code=status_code,
        error="internal_error",
        detail=SERVER_ERROR_MESSAGE,
    )
