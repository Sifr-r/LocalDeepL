"""Shim for the historical ``test_docuverse_upgrade`` test monolith.

The original 903-line file has been split by source module into:

- ``test_block_tree.py`` — :mod:`omniscribe.core.block_tree`
- ``test_glossary.py`` — :mod:`omniscribe.core.glossary`
- ``test_entity_memory.py`` — :mod:`omniscribe.core.entity_memory`
- ``test_handwriting_preprocessor.py`` — :mod:`omniscribe.core.handwriting_preprocessor`
- ``test_translation_tree.py`` — :mod:`omniscribe.core.translation_tree`
- ``test_html_writer.py`` — :mod:`omniscribe.core.html_writer`
- ``test_docx_tree_writer.py`` — :mod:`omniscribe.core.docx_tree_writer`
- ``test_tree_export.py`` — :mod:`omniscribe.core.tree_export`
- ``test_dual_translator.py`` — :mod:`omniscribe.core.dual_translator`
- ``test_trocr_engine.py`` — :mod:`omniscribe.core.trocr_engine`
- ``test_nllb_engine.py`` — :mod:`omniscribe.core.nllb_engine`

The ``translate_node`` test was merged into ``test_translation_boundary.py``
(where the other ``omniscribe.core.translation`` ``translate_node`` tests live).

This shim intentionally re-exports nothing to avoid duplicate test names during
pytest collection. New tests for the same modules should be added to the
target file above, not back here.
"""
