"""Audit-secondary F26 / Phase 2 fix: TableNode cells are translated.

Originally bundled in ``test_phase2_remediations.py``. Split
into its own file for 1:1 traceability — a regression here
must surface as a single, named test failure rather than
disappear into a 7-test omnibus.

The original fix: ``translate_tree`` (in
``omniscribe.core.translation_tree``) was previously bypassing
TableNode instances in ``page.children``, leaving table cells
untranslated. The fix recurses into ``TableNode.cells``.
"""

from __future__ import annotations

from omniscribe.core.block_tree import (
    BlockNode,
    BlockType,
    DocumentTree,
    PageTree,
    TableNode,
)
from omniscribe.core.translation_tree import translate_tree


async def test_translate_tree_translates_table_node_cells():
    """Verify TableNode cells are visited, translated, and emitted in on_translate_chunk."""
    cell_1 = BlockNode(
        block_type=BlockType.TABLE,
        bbox=(0.0, 0.0, 0.5, 0.5),
        text="Hello",
        page_idx=0,
    )
    cell_2 = BlockNode(
        block_type=BlockType.TABLE,
        bbox=(0.5, 0.0, 1.0, 0.5),
        text="World",
        page_idx=0,
    )
    table = TableNode(
        rows=1,
        cols=2,
        page_idx=0,
        bbox=(0.0, 0.0, 1.0, 0.5),
        cells=[[cell_1, cell_2]],
    )
    page = PageTree(page_idx=0, children=[table])
    tree = DocumentTree(pages=[page])

    async def mock_translator(prompt: str, target_lang: str, **kwargs) -> str:
        # Extract source text from the prompt or return a translated string
        if "SOURCE:\nHello" in prompt:
            return "Hola"
        if "SOURCE:\nWorld" in prompt:
            return "Mundo"
        return f"Translated_{target_lang}"

    chunk_events: list[tuple[int, int, str, str]] = []

    async def on_chunk(chunk_idx: int, source_chars: int, translated: str, lang: str):
        chunk_events.append((chunk_idx, source_chars, translated, lang))

    await translate_tree(
        tree,
        target_language="Spanish",
        translator=mock_translator,
        on_translate_chunk=on_chunk,
    )

    assert cell_1.text == "Hola"
    assert cell_1.metadata["translation"] == "Hola"
    assert cell_2.text == "Mundo"
    assert cell_2.metadata["translation"] == "Mundo"
    assert len(chunk_events) == 2
    assert chunk_events[0] == (0, 4, "Hola", "Spanish")
    assert chunk_events[1] == (1, 5, "Mundo", "Spanish")
