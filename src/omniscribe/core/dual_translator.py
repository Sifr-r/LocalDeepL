"""Dual-translator helper.

Runs two ``TranslatorFn`` implementations against the same prompt and picks
the one whose output is closer in length to the source (cheap proxy for
"didn't hallucinate / drop content").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omniscribe.core.translation_tree import TranslatorFn


async def dual_translate(
    text: str,
    *,
    target_language: str,
    primary: TranslatorFn,
    secondary: TranslatorFn,
    build_prompt: Callable[[str, str], str] | None = None,
) -> tuple[str, dict[str, object]]:
    """Translate ``text`` with both translators and pick the better candidate.

    Returns the chosen translation and a metadata dict with both candidates
    and their length ratios.
    """
    if build_prompt is None:

        async def _default(prompt: str, lang: str) -> str:
            return await primary(prompt, lang)

        # Without a custom prompt builder we can't use the secondary easily;
        # fall back to primary.
        out = await primary(text, target_language)
        return out, {"primary": out, "secondary": None, "strategy": "single"}

    p_prompt = build_prompt(text, target_language)
    primary_text, secondary_text = await _gather(
        primary(p_prompt, target_language), secondary(p_prompt, target_language)
    )
    src_len = max(1, len(text))
    p_ratio = abs(len(primary_text) - src_len) / src_len
    s_ratio = abs(len(secondary_text) - src_len) / src_len
    chosen = secondary_text if s_ratio < p_ratio else primary_text
    return chosen, {
        "primary": primary_text,
        "secondary": secondary_text,
        "primary_length_ratio": p_ratio,
        "secondary_length_ratio": s_ratio,
        "strategy": "dual",
    }


async def _gather(*coros: Awaitable[str]) -> list[str]:
    import asyncio

    return list(await asyncio.gather(*coros))
