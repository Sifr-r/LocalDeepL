"""Tests for :mod:`omniscribe.core.translate.dual`."""

from __future__ import annotations

from omniscribe.core.translate.dual import dual_translate


async def test_dual_translate_chooser():
    async def primary(prompt: str, lang: str) -> str:
        return "this is a very long and unhelpful translation that pads the output"

    async def secondary(prompt: str, lang: str) -> str:
        return "salut mon ami"

    def build_prompt(text: str, lang: str) -> str:
        return f"Translate to {lang}: {text}"

    chosen, meta = await dual_translate(
        "hi",
        target_language="French",
        primary=primary,
        secondary=secondary,
        build_prompt=build_prompt,
    )
    assert meta["strategy"] == "dual"
    # secondary (3 words, very close to "hi") should be chosen
    assert chosen == "salut mon ami"
    assert meta["primary_length_ratio"] > meta["secondary_length_ratio"]  # type: ignore[operator]


async def test_dual_translate_falls_back_when_no_prompt_builder():
    async def primary(prompt: str, lang: str) -> str:
        return "primary result"

    chosen, meta = await dual_translate(
        "hi", target_language="French", primary=primary, secondary=primary
    )
    assert chosen == "primary result"
    assert meta["strategy"] == "single"
