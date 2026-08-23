"""Document-level entity memory for translation.

Extracts proper nouns, dates, and named entities from the source text and
re-injects them as a context block in every subsequent chunk's translation
prompt. This is the single highest-leverage quality fix for the
"the protagonist's name drifts mid-document" problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Common stopwords (English-only stoplist — multilingual stopwords would
# bloat the per-chunk context block).
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "while",
        "with",
        "without",
        "for",
        "from",
        "of",
        "on",
        "in",
        "at",
        "to",
        "by",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "their",
        "there",
        "here",
        "where",
        "when",
        "who",
        "what",
        "which",
        "he",
        "she",
        "they",
        "them",
        "his",
        "her",
        "him",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "mine",
    ]
)

# Naive date pattern: matches 2024-01-09, 1/9/2024, Jan 9 2007, etc.
_DATE_RE = re.compile(
    r"\b("
    r"\d{4}-\d{2}-\d{2}"  # 2024-01-09
    r"|\d{1,2}/\d{1,2}/\d{2,4}"  # 1/9/2024
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{2,4}"
    r")\b",
    re.IGNORECASE,
)

# Naive proper-noun pattern: capitalized words not at sentence start.
# This is approximate; for production a spaCy NER model would be better.
_PROPER_RE = re.compile(
    r"(?<![\.\!\?]\s)(?<!^)(?<=\s)([A-Z][a-zA-Z'\-]{1,}(?:\s+[A-Z][a-zA-Z'\-]{1,})*)"
)


@dataclass(slots=True)
class EntityMemory:
    """In-memory bag of named entities and dates extracted from a document."""

    names: set[str] = field(default_factory=set)
    dates: set[str] = field(default_factory=set)
    acronyms: set[str] = field(default_factory=set)

    def add_text(self, text: str) -> None:
        for m in _DATE_RE.findall(text):
            self.dates.add(m)
        for m in _PROPER_RE.findall(text):
            if m.lower() in _STOPWORDS:
                continue
            # Acronyms (all-caps, length 2..6) get their own bucket.
            stripped = m.strip()
            if 2 <= len(stripped) <= 6 and stripped.isupper():
                self.acronyms.add(stripped)
            else:
                self.names.add(stripped)

    def merge(self, other: EntityMemory) -> EntityMemory:
        merged = EntityMemory(
            names=set(self.names) | set(other.names),
            dates=set(self.dates) | set(other.dates),
            acronyms=set(self.acronyms) | set(other.acronyms),
        )
        return merged

    def to_prompt_block(self) -> str:
        """Return a context block suitable for injection into a translation prompt."""
        parts: list[str] = []
        if self.names:
            parts.append(
                "PROPER NOUNS (use these names consistently):\n"
                + "\n".join(f"- {n}" for n in sorted(self.names))
            )
        if self.dates:
            parts.append(
                "DATES (preserve the original date format when possible):\n"
                + "\n".join(f"- {d}" for d in sorted(self.dates))
            )
        if self.acronyms:
            parts.append(
                "ACRONYMS (preserve capitalization):\n"
                + "\n".join(f"- {a}" for a in sorted(self.acronyms))
            )
        return "\n\n".join(parts)

    def is_empty(self) -> bool:
        return not (self.names or self.dates or self.acronyms)
