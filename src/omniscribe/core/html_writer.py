"""HTML export from :class:`DocumentTree`.

Implements the Azure Document Intelligence Markdown element vocabulary so the
output is round-trippable between HTML and DOCX:

- ``<h1>``..``<h6>`` for section headers
- ``<table>`` with ``<thead>`` / ``<tbody>`` (not pipe-tables)
- ``<figure>`` + ``<figcaption>`` for images
- ``<pre><code>`` for code blocks, ``<code>`` for inline
- ``<math>`` (MathML) for equations
- ``<!-- PageBreak -->`` markers between pages
- ``data-block-id`` and ``data-bbox`` on every block for the UI to re-bind
"""

from __future__ import annotations

import base64
import html
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omniscribe.core.block_tree import (
        BlockNode,
        DocumentTree,
        PageTree,
        TableNode,
    )


def render_html(tree: DocumentTree) -> str:
    """Render a :class:`DocumentTree` to a single HTML string."""
    out: list[str] = []
    out.append("<!DOCTYPE html>")
    out.append('<html lang="en">')
    out.append("<head>")
    out.append('<meta charset="utf-8">')
    title = tree.source_path or "Document"
    out.append(f"<title>{html.escape(title)}</title>")
    out.append(_embedded_css())
    out.append("</head><body>")
    for i, page in enumerate(tree.pages):
        if i > 0:
            out.append("<!-- PageBreak -->")
        out.append(_render_page(page))
    # Tables live on the tree (``tree.tables``) rather than on a page's
    # children — the table-extraction processor builds ``TableNode``s and
    # filters the cell blocks back out of ``page.children``, so this loop is
    # the only place a ``<table>`` is emitted. The corresponding figure and
    # equation elements are rendered via the page-walk above (``_render_block``
    # branches on ``block_type == "figure" | "equation"``); rendering them
    # again from ``tree.figures`` / ``tree.equations`` would duplicate the
    # markup, so those post-walks were removed.
    for table in tree.tables:
        out.append(_render_table(table))
    out.append("</body></html>")
    return "\n".join(out)


def _embedded_css() -> str:
    return (
        "<style>"
        "body{font-family:Georgia,'Times New Roman',serif;max-width:780px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.55;color:#111}"
        "h1,h2,h3,h4,h5,h6{margin-top:1.4em;line-height:1.2}"
        "table{border-collapse:collapse;margin:1em 0;width:100%}"
        "th,td{border:1px solid #ccc;padding:.4em .6em;text-align:left;vertical-align:top}"
        "th{background:#f3f3f3}"
        "figure{margin:1.2em 0;text-align:center}"
        "figcaption{font-size:.9em;color:#666;margin-top:.3em}"
        "pre{background:#f3f3f3;padding:.8em;overflow-x:auto;border-radius:4px}"
        "code{font-family:Menlo,Consolas,monospace;font-size:.9em}"
        "math{font-family:'Cambria Math',serif}"
        "[data-bbox]{display:block}"
        "ul,ol{padding-left:1.4em}"
        "</style>"
    )


def _render_page(page: PageTree) -> str:
    parts: list[str] = []
    parts.append(f'<section data-page-idx="{page.page_idx}">')
    for child in page.children:
        parts.append(_render_block(child))
    parts.append("</section>")
    return "\n".join(parts)


def _render_block(node: BlockNode) -> str:
    data = (
        f' data-block-id="{node.block_id}"'
        f' data-bbox="{",".join(f"{v:.4f}" for v in node.bbox)}"'
    )
    if node.confidence is not None:
        data += f' data-confidence="{node.confidence:.3f}"'

    if node.block_type.value == "section_header":
        level = max(1, min(6, node.level or 1))
        tag = f"h{level}"
        return f"<{tag}{data}>{html.escape(node.text)}</{tag}>"
    if node.block_type.value == "list_item":
        depth = max(0, node.level)
        tag = "ul" if depth == 0 else f"ul data-depth='{depth}'"
        return f"<li{data}>{html.escape(node.text)}</li>"
    if node.block_type.value == "code":
        return f"<pre{data}><code>{html.escape(node.text)}</code></pre>"
    if node.block_type.value == "equation":
        latex = html.escape(getattr(node, "latex", None) or node.text)
        return f"<span{data}><code>{latex}</code></span>"
    if node.block_type.value == "figure":
        img_html = ""
        # Figures can be either a BlockNode (caption-only) or a FigureNode
        # (image_bytes + caption). Handle both.
        image_bytes = getattr(node, "image_bytes", None)
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            img_html = f'<img src="data:image/png;base64,{b64}" alt="">'
        elif node.text and (
            node.text.startswith("http") or node.text.startswith("data:")
        ):
            img_html = f'<img src="{html.escape(node.text)}" alt="">'
        caption = (
            getattr(node, "caption", None) or node.metadata.get("caption", "") or ""
        )
        if (
            not caption
            and node.text
            and not (node.text.startswith("http") or node.text.startswith("data:"))
        ):
            caption = node.text
        cap = html.escape(caption)
        return f"<figure{data}>{img_html}<figcaption>{cap}</figcaption></figure>"
    if node.block_type.value == "table":
        return _render_table(node)  # type: ignore[arg-type]
    if node.block_type.value == "page_header":
        return f"<!-- PageHeader={html.escape(node.text)} -->"
    if node.block_type.value == "page_footer":
        return f"<!-- PageFooter={html.escape(node.text)} -->"
    if node.block_type.value == "page_number":
        return f"<!-- PageNumber={html.escape(node.text)} -->"

    text = _render_spans(node)
    return f"<p{data}>{text}</p>"


def _render_spans(node: BlockNode) -> str:
    if not node.spans:
        return html.escape(node.text)
    out: list[str] = []
    for sp in node.spans:
        s = html.escape(sp.text)
        if sp.bold and sp.italic:
            s = f"<strong><em>{s}</em></strong>"
        elif sp.bold:
            s = f"<strong>{s}</strong>"
        elif sp.italic:
            s = f"<em>{s}</em>"
        if sp.code:
            s = f"<code>{s}</code>"
        out.append(s)
    return "".join(out)


def _render_table(table: TableNode) -> str:
    rows: list[str] = []
    for r_idx, row in enumerate(table.cells):
        cells: list[str] = []
        for c in row:
            cells.append(
                "<td"
                + f' data-block-id="{c.block_id}"'
                + f">{html.escape(c.text)}</td>"
            )
        # for header row swap td->th
        if r_idx == 0:
            cells = [c.replace("<td", "<th").replace("</td>", "</th>") for c in cells]
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        f'<table data-block-id="{table.block_id}" '
        f'data-rows="{table.rows}" data-cols="{table.cols}">'
        + f"<tbody>{''.join(rows)}</tbody></table>"
    )


def iter_blocks(tree: DocumentTree) -> Iterable[BlockNode]:
    for page in tree.pages:
        for child in page.children:
            yield from _walk(child)


def _walk(node: BlockNode) -> Iterable[BlockNode]:
    yield node
    for c in node.children:
        yield from _walk(c)
