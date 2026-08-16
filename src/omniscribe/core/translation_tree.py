"""Tree-aware translation.

Walks a :class:`DocumentTree`, translates each text block (preserving
structure), and writes the translation back into the tree. This is the
foundation for structure-preserving translation: headings stay headings,
tables stay tables, figures stay figures.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from omniscribe.core.entity_memory import EntityMemory
from omniscribe.core.glossary import Glossary
from omniscribe.utils.prompt_safety import sanitize_prompt_input

if TYPE_CHECKING:
    from omniscribe.core.block_tree import BlockNode, DocumentTree
    from omniscribe.core.callbacks import TranslateChunkCallback
    from omniscribe.core.translation_config import TranslationSettings

logger = logging.getLogger(__name__)


# A pluggable async callable that takes a prompt and returns translated text.
TranslatorFn = Callable[[str, str], Awaitable[str]]


def build_context_block(
    glossary: Glossary,
    memory: EntityMemory,
    sliding_window: str = "",
) -> str:
    parts: list[str] = []
    gb = glossary.to_prompt_block()
    if gb:
        parts.append(gb)
    mb = memory.to_prompt_block()
    if mb:
        parts.append(mb)
    if sliding_window:
        parts.append(
            "PREVIOUS CONTEXT (do not translate again, just stay consistent):\n"
            + sliding_window
        )
    return "\n\n".join(parts)


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[-max_words:])


_SKIP_TYPES = {
    "page_header",
    "page_footer",
    "page_number",
    "figure",
}


async def translate_tree(
    tree: DocumentTree,
    *,
    target_language: str,
    translator: TranslatorFn,
    settings: TranslationSettings | None = None,
    glossary: Glossary | None = None,
    memory: EntityMemory | None = None,
    sliding_window_words: int = 80,
    dual_translate: bool = False,
    second_translator: TranslatorFn | None = None,
    on_translate_chunk: TranslateChunkCallback | None = None,
) -> DocumentTree:
    """Translate every text-bearing block in a :class:`DocumentTree`.

    ``translator(prompt, target_language) -> translated_text`` is the only
    LLM hook. The caller wires it up to the configured LLM (sync or async
    translation path), NLLBEngine, or any other back-end.

    The function:

    - Walks every page's children in order
    - Skips ``PAGE_HEADER`` / ``PAGE_FOOTER`` / ``PAGE_NUMBER`` / ``FIGURE`` blocks
    - Builds a per-chunk prompt that injects glossary, entity memory, and
      the last ``sliding_window_words`` words of the previous translation
    - Writes the result back into ``block.text`` and ``block.metadata["translation"]``

    If ``on_translate_chunk`` is supplied, it is invoked once per
    successfully translated block with
    ``(chunk_idx, source_chars, translated_text, target_language)``.
    The callback fires only for blocks whose translation actually
    replaced the source text (skipped / empty / page-header blocks
    are silent). This is the contract the live UI subscribes to
    through ``manager.send_translate_chunk``; programmatic callers
    can pass any coroutine (e.g. a logging sink) or omit the kwarg
    entirely to disable the observer.
    """

    glossary = glossary or Glossary()
    memory = memory or EntityMemory()
    last_window = ""
    chunk_idx = 0

    for page in tree.pages:
        for node in page.children:
            translated_text, last_window = await _translate_node(
                node,
                target_language=target_language,
                translator=translator,
                glossary=glossary,
                memory=memory,
                last_window=last_window,
                sliding_window_words=sliding_window_words,
                dual_translate=dual_translate,
                second_translator=second_translator,
            )
            if translated_text is not None:
                node.text = translated_text
                node.metadata["translation"] = translated_text
                if on_translate_chunk is not None:
                    # The chunk index is a per-call counter, not a
                    # global one — each translate_tree() invocation
                    # restarts from 0. Consumers that need a
                    # document-wide index can compute it from the
                    # block's tree position.
                    source_chars = len(node.text)
                    await on_translate_chunk(
                        chunk_idx,
                        source_chars,
                        translated_text,
                        target_language,
                    )
                    chunk_idx += 1
    return tree


async def _translate_node(
    node: BlockNode,
    *,
    target_language: str,
    translator: TranslatorFn,
    glossary: Glossary,
    memory: EntityMemory,
    last_window: str,
    sliding_window_words: int,
    dual_translate: bool,
    second_translator: TranslatorFn | None,
) -> tuple[str | None, str]:
    if node.block_type.value in _SKIP_TYPES:
        return None, last_window
    if not node.text or not node.text.strip():
        return None, last_window

    # Update entity memory as we go.
    memory.add_text(node.text)

    context = build_context_block(glossary, memory, last_window)
    prompt = _build_translation_prompt(
        text=node.text,
        target_language=target_language,
        context=context,
        block_type=node.block_type.value,
    )

    primary = await translator(prompt, target_language)
    primary = _clean_translation(primary, source=node.text)

    if dual_translate and second_translator is not None:
        secondary = await second_translator(prompt, target_language)
        secondary = _clean_translation(secondary, source=node.text)
        # Pick the candidate that is closer in length to the source (cheap
        # proxy for "didn't drop or hallucinate content").
        if abs(len(secondary) - len(node.text)) < abs(len(primary) - len(node.text)):
            chosen = secondary
        else:
            chosen = primary
    else:
        chosen = primary

    new_window = _truncate_words(chosen, sliding_window_words)
    return chosen, new_window


def _build_translation_prompt(
    *, text: str, target_language: str, context: str, block_type: str
) -> str:
    # Sanitize the user-controlled text once. Control characters and
    # boundary markers are the realistic injection vectors for a
    # document that already passed OCR; sanitize rather than escape
    # per-injection-site so a future block type can't forget.
    safe_text = sanitize_prompt_input(text)
    type_hint = ""
    if block_type == "section_header":
        type_hint = (
            "\nNOTE: This is a document heading. Translate it as a concise heading; "
            "do not add punctuation.\n"
        )
    elif block_type == "list_item":
        type_hint = (
            "\nNOTE: This is a list item. Keep it terse; preserve list semantics.\n"
        )
    elif block_type == "code":
        return (
            f"Translate only the natural-language parts of the following code block. "
            f"Do not translate code identifiers, function names, or string literals. "
            f"Target language: {target_language}.\n\n"
            f"```\n{safe_text}\n```\n"
        )
    elif block_type == "key_value":
        type_hint = (
            "\nNOTE: This is a key-value pair. Translate only the value; keep keys "
            "intact if they're labels (e.g. 'Invoice Number').\n"
        )

    if context:
        return (
            f"Translate the following text into {target_language}. "
            f"Preserve formatting, line breaks, and any inline runs.\n"
            f"{type_hint}\n"
            f"{context}\n\n"
            f"SOURCE:\n{safe_text}\n\n"
            f"TRANSLATION ({target_language}):"
        )
    return (
        f"Translate the following text into {target_language}. "
        f"Preserve formatting, line breaks, and any inline runs.\n"
        f"{type_hint}\n"
        f"SOURCE:\n{safe_text}\n\n"
        f"TRANSLATION ({target_language}):"
    )


# Common LLM preambles to strip from translation outputs.
_PREAMBLE_PATTERNS = [
    re.compile(
        r"^\s*(?:Here(?:'s| is) the translation|Translation|Sure[,!]?)[^\n]*\n+",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*```[a-zA-Z]*\n+"),
    re.compile(r"\n+\s*```\s*$"),
]


def _clean_translation(text: str, *, source: str) -> str:
    if not text:
        return text
    out = text.strip()
    for pat in _PREAMBLE_PATTERNS:
        out = pat.sub("", out)
    return out.strip()
