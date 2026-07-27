"""TMX 1.4 and later glossary parser."""

from __future__ import annotations

from ._common import (
    decode_source,
    entry_dict,
    finalize,
    iter_text,
    language_matches,
    local_name,
    require_bytes,
    safe_xml_root,
)
from .summary import GlossaryImportSummary

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def parse_tmx(
    data: bytes,
    *,
    encoding: str | None = None,
    source_lang: str = "en",
) -> GlossaryImportSummary:
    """Pair each source-language TMX segment with the first target segment."""
    raw = require_bytes(data)
    _text, used_encoding, warnings = decode_source(raw, encoding)
    root = safe_xml_root(raw)
    entries: list[dict[str, object]] = []

    for translation_unit in root.iter():
        if local_name(translation_unit.tag) != "tu":
            continue
        variants: list[tuple[str | None, str]] = []
        for variant in translation_unit:
            if local_name(variant.tag) != "tuv":
                continue
            language = variant.attrib.get(_XML_LANG) or variant.attrib.get("lang")
            segment = next(
                (child for child in variant if local_name(child.tag) == "seg"),
                None,
            )
            value = iter_text(segment)
            if value:
                variants.append((language, value))
        if not variants:
            continue
        source = next(
            (value for language, value in variants if language_matches(language, source_lang)),
            variants[0][1],
        )
        target = next(
            (
                value
                for language, value in variants
                if value != source
                and not language_matches(language, source_lang)
            ),
            "",
        )
        item = entry_dict(source, target)
        if item is not None:
            entries.append(item)

    if not entries:
        raise ValueError("TMX source contains no bilingual translation units.")
    return finalize(
        entries,
        format_name="tmx",
        encoding=used_encoding,
        warnings=warnings,
    )
