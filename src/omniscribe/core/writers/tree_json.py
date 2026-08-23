"""Block-tree JSON export.

This module is intentionally tiny: a :class:`DocumentTree` already carries
all the structural data needed for downstream tooling. The :func:`export_json`
helper just round-trips it through :meth:`DocumentTree.to_dict` with a
sane JSON encoder.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omniscribe.core.block_tree import DocumentTree


def export_json(tree: DocumentTree, *, indent: int | None = 2) -> str:
    """Serialize a :class:`DocumentTree` to a JSON string.

    Image bytes in figures are base64-encoded so the output is JSON-clean.
    """
    payload = tree.to_dict()
    # base64-encode image bytes so they survive JSON round-trip
    for fig in payload.get("figures", []):
        if isinstance(fig.get("image_bytes_b64"), bytes):
            fig["image_bytes_b64"] = base64.b64encode(fig["image_bytes_b64"]).decode(
                "ascii"
            )
    return json.dumps(payload, indent=indent, ensure_ascii=False)


def export_json_bytes(tree: DocumentTree, *, indent: int | None = None) -> bytes:
    return export_json(tree, indent=indent).encode("utf-8")
