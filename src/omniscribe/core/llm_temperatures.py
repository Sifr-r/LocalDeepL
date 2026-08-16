"""Centralized LLM temperature constants for OmniScribe.

Each OmniScribe call site has a different tolerance for generation
variation. Picking a temperature is not arbitrary — it is a contract
about how much the model is allowed to deviate from the most-likely
completion. The values below were tuned for the local-model
deployment shape (LM Studio + OlmOCR-2 / Qwen3-VL) and have a
documented rationale per call site. If you are adding a new call
site, pick the existing constant that best matches your tolerance
rather than inventing a new float — that way the next reader can
read the rationale once and reason about every call site.

The values are not env-overridable by design. They are deployment
shape, not user preference. Operators who need a different value
should add a new named constant here, not a runtime knob.
"""

from __future__ import annotations

#: OCR (page-level + per-crop). The output is read verbatim and fed
#: into the alignment / refinement stages; any non-deterministic
#: variation that survives the filter layer causes the same image
#: to produce different downstream bboxes on re-runs. 0.1 lets the
#: model recover from degenerate-token traps (e.g. repeating a
#: line forever) without injecting real randomness.
TEMPERATURE_OCR: float = 0.1

#: Same reasoning as :data:`TEMPERATURE_OCR`. The grounded VLM
#: backend tends to produce extremely low-entropy outputs (often
#: well below the OCR path) once it's seen a few examples, so we
#: can afford the strictest setting.
TEMPERATURE_GROUNDED: float = 0.0

#: Structured extraction (invoice / resume / academic / custom).
#: The model is expected to return a deterministic JSON object;
#: any temperature above 0.1 invites the LLM to "creatively"
#: fabricate fields. Same as OCR: just enough to escape degenerate
#: generation, not enough to fabricate.
TEMPERATURE_EXTRACTION: float = 0.1

#: Translation quality evaluator (LLM-as-judge). Stable scoring
#: across reruns is essential — a 0.92 today and a 0.71 tomorrow
#: on the same input would burn operator trust in the loop. 0.1.
TEMPERATURE_EVALUATION: float = 0.1

#: Translation — chunked, sync, single-shot. The local model
#: needs room to pick a natural-sounding target-language phrasing
#: without every call collapsing onto the same high-probability
#: token sequence. 0.3 matches the DeepL sweet spot and keeps
#: glossary consistency stable when the RAG context pins the
#: terms.
TEMPERATURE_TRANSLATION: float = 0.3

#: Translation — tree-based with sliding-window continuity. The
#: sliding window already constrains the variation (each chunk
#: is conditioned on the previous translation), so the per-call
#: temperature can be lower than the standalone path. 0.2 — any
#: lower and the model starts repeating the previous chunk
#: verbatim.
TEMPERATURE_TRANSLATION_TREE: float = 0.2


__all__ = [
    "TEMPERATURE_EVALUATION",
    "TEMPERATURE_EXTRACTION",
    "TEMPERATURE_GROUNDED",
    "TEMPERATURE_OCR",
    "TEMPERATURE_TRANSLATION",
    "TEMPERATURE_TRANSLATION_TREE",
]
