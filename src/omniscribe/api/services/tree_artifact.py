"""JSON-based DocumentTree artifact I/O.

Replaces the previous pickle round-trip (see review M4). Pickle was
opaque to debugging and a deserialization RCE footgun if the artifact
path was ever exposed across a trust boundary. JSON is debuggable
(cat the file, see the content), bounded (no `__reduce__` exploitation),
and forward-compatible (the next IR revision just adds a key — old
readers can ignore it via `data.get(...)`).

Two operations:
  * :func:`write_tree_atomic` — write a tree to a `.tree.json` file
    via tempfile + rename, so a crash mid-write never leaves a
    partial file behind.
  * :func:`read_tree` — read a tree back. Raises
    :class:`TreeArtifactError` (a subclass of :class:`ValueError`)
    on any schema mismatch; never executes arbitrary code.

The artifact is scoped to the server's temp directory and bound to
an opaque artifact ID + token (see :class:`TextArtifactStore`).
The token check is the security boundary; this module is just
"safe to deserialize."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omniscribe.core.block_tree import DocumentTree


class TreeArtifactError(ValueError):
    """Raised when a tree artifact file is missing, unreadable, or
    has the wrong shape. Subclasses `ValueError` so callers that
    already handle `ValueError` from artifact lookups (e.g. HTTP
    404 mapping) keep working."""


def write_tree_atomic(tree: DocumentTree, path: Path) -> None:
    """Serialize ``tree`` to ``path`` as UTF-8 JSON.

    Writes to a sibling ``.tmp`` file first, then atomically renames
    it to ``path``. A crash mid-write either leaves the previous
    file untouched (rename never happened) or leaves a ``.tmp``
    behind (no partial ``path``); readers either get the old
    content or fail cleanly.

    The JSON is pretty-printed (indent=2) because artifact files
    are human-debuggable artifacts — disk space is cheap, opaque
    blobs are not. ``ensure_ascii=False`` so non-ASCII document
    content (Arabic, Chinese, etc.) stays readable in the file
    rather than being escaped to ``\\uXXXX``.
    """
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(
        tree.to_dict(),
        indent=2,
        ensure_ascii=False,
        # `default` is not set on purpose: every field of the tree
        # IR is JSON-native (str, int, float, list, dict, None, or
        # base64-encoded bytes inside FigureNode). If you add a
        # non-native field, prefer extending the encoder to
        # bouncing on `default=` — silent failure on serialization
        # is the wrong failure mode for an artifact.
    )
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def read_tree(path: Path) -> DocumentTree:
    """Load a :class:`DocumentTree` from a JSON file at ``path``.

    Raises:
      * :class:`FileNotFoundError` — ``path`` does not exist. (Not
        wrapped: callers that already handle ``FileNotFoundError``
        for "artifact not found" keep working unchanged.)
      * :class:`TreeArtifactError` (a :class:`ValueError` subclass) —
        the file exists but is unreadable as a tree artifact:
        bad JSON, wrong root type, or schema mismatch.

    Never executes arbitrary code (the previous pickle-based loader
    would call ``__reduce__`` on whatever class the artifact
    happened to contain — a real RCE footgun if the artifact path
    were ever exposed across a trust boundary).
    """
    path = Path(path)
    # `read_text` raises `FileNotFoundError` for a missing file —
    # let it bubble unchanged so callers that already map
    # FileNotFoundError to "artifact not found" (HTTP 404, etc.)
    # don't have to learn a new exception type for the same case.
    raw = path.read_text(encoding="utf-8")
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TreeArtifactError(
            f"Tree artifact {path} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise TreeArtifactError(
            f"Tree artifact {path} root must be a JSON object, "
            f"got {type(data).__name__}"
        )
    try:
        return DocumentTree.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        # KeyError: missing required field (e.g. "pages").
        # TypeError: field present but wrong shape (e.g. list[str]
        #   expected, list[dict] given).
        # ValueError: field present but invalid (e.g. block_type
        #   string not in the BlockType enum).
        raise TreeArtifactError(
            f"Tree artifact {path} does not match DocumentTree schema: {exc}"
        ) from exc


__all__ = ["TreeArtifactError", "read_tree", "write_tree_atomic"]
