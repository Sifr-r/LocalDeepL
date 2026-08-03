"""Output sanitization filters for LLM OCR responses.

Each filter handles a *distinct* failure mode we've observed in production
with local vision LLMs (OlmOCR, GLM-OCR, etc.):

- :data:`_HALLUCINATION_PATTERNS` / :func:`_is_fallback_response` — the
  model emitted a known fallback phrase ("lorem ipsum", the
  OlmOCR-2 pangram). Substring match would over-trigger on real
  documents containing those phrases as quotes, so we require the
  fallback to dominate the response.
- :func:`_strip_yaml_front_matter` — OlmOCR emits a YAML front
  matter block per its prompt; we want the markdown body, not the
  metadata tags.
- :func:`_strip_runaway_repetition` — local VLMs occasionally get
  stuck emitting the same line in a loop. We cap occurrences so one
  bad page doesn't fill the response buffer.

Filters are pure functions; they have no I/O and no model dependencies,
so they're safe to unit-test without mocking the LLM.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# Phrases the model emits as a fallback when it can't read the crop —
# usually because the crop is blank, decorative, or otherwise non-text.
# We strip them so they don't pollute the searchable text layer.
_HALLUCINATION_PATTERNS = (
    "the quick brown fox jumps over the lazy dog",  # OlmOCR-2 pangram fallback
    "lorem ipsum",
)


def _is_fallback_response(text: str) -> bool:
    """Return True if ``text`` is essentially one of the known LLM fallback phrases.

    A substring match would over-trigger: a real document might contain
    "lorem ipsum" as quoted placeholder text, or the pangram as an
    example sentence. We require the response to *be* the fallback
    after light normalization (case-fold, strip whitespace, drop
    surrounding punctuation/quotes) — i.e. the fallback occupies the
    entire crop response, not just part of it.
    """
    _trim = ".!?\"'`)([]{}<>“”‘’ \t"
    normalized = text.strip().lower().strip(_trim)
    return normalized in _HALLUCINATION_PATTERNS


def _strip_yaml_front_matter(text: str) -> str:
    """Return the body that follows an optional OlmOCR YAML front matter block.

    If the response begins with a YAML front matter block (--- ... ---),
    return the body after it. Otherwise return the input unchanged.
    Robust to models that ignore the front-matter instruction or wrap it
    in markdown code fences.
    """
    t = re.sub(r"^\s*```[a-zA-Z]*\n?", "", text).lstrip()
    if not t.startswith("---"):
        return text
    # Find the closing fence on its own line, after the opening fence.
    rest = t[3:]
    close_idx = rest.find("\n---")
    if close_idx == -1:
        return text  # malformed; return as-is
    body = rest[close_idx + len("\n---") :]
    # Remove optional closing ``` if it was part of a markdown fence
    body = re.sub(r"^\s*```\n?", "", body)
    # Trim the newline directly after the closing fence.
    return body.lstrip("\n").strip()


def _strip_runaway_repetition(lines: list[str], max_repeat: int = 20) -> list[str]:
    """Drop pathological repetition from LLM output.

    Local VLMs occasionally fall into an output loop on dense or unusual
    pages — the same line is emitted dozens or hundreds of times in a row
    until max_tokens cuts the response off. The repeated junk pollutes
    every box the DP then tries to assign it to. We cap any single string
    at ``max_repeat`` total occurrences across the response: large enough
    to admit legitimate repeated structure (table row tags, separators)
    but small enough that runaway loops are clipped to a handful of lines
    and the rest is dropped.

    A warning is emitted if any clipping happened so the user knows the
    OCR layer for that page may be incomplete.
    """
    counts: dict[str, int] = {}
    out: list[str] = []
    truncated = 0
    for line in lines:
        c = counts.get(line, 0) + 1
        counts[line] = c
        if c <= max_repeat:
            out.append(line)
        else:
            truncated += 1
    if truncated > 0:
        worst = max(counts.items(), key=lambda kv: kv[1])
        logger.warning(
            "LLM OCR output had %d runaway-repetition lines clipped "
            "(worst offender: %r occurred %d times). The model likely "
            "got stuck on this page; output may be incomplete. "
            "Try lowering --max-image-dim or switching --model.",
            truncated,
            worst[0][:60],
            worst[1],
        )
    return out


__all__ = [
    "_HALLUCINATION_PATTERNS",
    "_is_fallback_response",
    "_strip_runaway_repetition",
    "_strip_yaml_front_matter",
]
