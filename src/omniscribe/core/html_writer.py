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
from typing import TYPE_CHECKING, cast

from omniscribe.core.block_tree import TableNode

if TYPE_CHECKING:
    from omniscribe.core.block_tree import (
        BlockNode,
        DocumentTree,
        PageTree,
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
    rendered_table_ids: set[str] = set()
    for i, page in enumerate(tree.pages):
        if i > 0:
            out.append("<!-- PageBreak -->")
        out.append(_render_page(page, rendered_table_ids))
    for table in tree.tables:
        if table.block_id not in rendered_table_ids:
            out.append(_render_table(table))
            rendered_table_ids.add(table.block_id)
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


def _render_page(page: PageTree, rendered_table_ids: set[str] | None = None) -> str:
    parts: list[str] = []
    parts.append(f'<section data-page-idx="{page.page_idx}">')
    current_list: list[str] = []

    def flush_list() -> None:
        if current_list:
            parts.append("<ul>")
            parts.extend(current_list)
            parts.append("</ul>")
            current_list.clear()

    for child in page.children:
        if isinstance(child, TableNode):
            flush_list()
            if rendered_table_ids is not None:
                rendered_table_ids.add(child.block_id)
            parts.append(_render_table(child))
            continue

        bt = getattr(child, "block_type", None)
        bt_val = (
            bt.value if (bt is not None and hasattr(bt, "value")) else str(bt or "")
        )
        if bt_val == "list_item":
            current_list.append(_render_block(child))
        else:
            flush_list()
            if bt_val == "table":
                if rendered_table_ids is not None:
                    rendered_table_ids.add(child.block_id)
                if hasattr(child, "cells"):
                    parts.append(_render_table(cast("TableNode", child)))
            else:
                parts.append(_render_block(child))

    flush_list()
    parts.append("</section>")
    return "\n".join(parts)


def _render_block(node: BlockNode | TableNode) -> str:
    if isinstance(node, TableNode):
        return _render_table(node)
    bt = (
        node.block_type.value
        if hasattr(node.block_type, "value")
        else str(node.block_type)
    )
    if bt == "table":
        if hasattr(node, "cells"):
            return _render_table(cast("TableNode", node))
        return ""
    data = (
        f' data-block-id="{node.block_id}"'
        f' data-bbox="{",".join(f"{v:.4f}" for v in node.bbox)}"'
    )
    if node.confidence is not None:
        data += f' data-confidence="{node.confidence:.3f}"'

    if bt == "section_header":
        level = max(1, min(6, node.level or 1))
        tag = f"h{level}"
        return f"<{tag}{data}>{html.escape(node.text)}</{tag}>"
    if bt == "list_item":
        return f"<li{data}>{html.escape(node.text)}</li>"
    if bt == "code":
        return f"<pre{data}><code>{html.escape(node.text)}</code></pre>"
    if bt == "equation":
        latex = html.escape(getattr(node, "latex", None) or node.text)
        return f"<span{data}><code>{latex}</code></span>"
    if bt == "figure":
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
    if bt == "page_header":
        return f"<!-- PageHeader={html.escape(node.text)} -->"
    if bt == "page_footer":
        return f"<!-- PageFooter={html.escape(node.text)} -->"
    if bt == "page_number":
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
            if isinstance(child, BlockNode):
                yield from _walk(child)
            elif isinstance(child, TableNode):
                for row in child.cells:
                    for cell in row:
                        yield from _walk(cell)


def _walk(node: BlockNode) -> Iterable[BlockNode]:
    yield node
    for c in node.children:
        yield from _walk(c)
