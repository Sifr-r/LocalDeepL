"""Prompt constants and selection helpers for the OCR processor."""

from __future__ import annotations

# Canonical OlmOCR-2 prompt (the model was RL-trained on this exact string).
# Source: github.com/allenai/olmocr olmocr/prompts/prompts.py
# :func:`build_no_anchoring_v4_yaml_prompt`.
OLMOCR_PAGE_PROMPT = (
    "Attached is one page of a document that you must process. Just return "
    "the plain text representation of this document as if you were reading it "
    "naturally. Convert equations to LateX and tables to HTML.\n"
    "If there are any figures or charts, label them with the following "
    "markdown syntax ![Alt text describing the contents of the figure]"
    "(page_startx_starty_width_height.png)\n"
    "Return your output as markdown, with a front matter section on top "
    "specifying values for the primary_language, is_rotation_valid, "
    "rotation_correction, is_table, and is_diagram parameters."
)

# Prompt for cropped box regions — we want raw text only, no metadata
# (the YAML front matter is nonsensical for a single line/region).
CROP_PROMPT = """
You are a highly accurate OCR assistant.
Extract all text from the provided image crop exactly as it appears.
CRITICAL INSTRUCTION: Pay extremely close attention to all diacritical marks (e.g. Arabic Tashkeel, French accents, German umlauts). They are deliberate and must be transcribed accurately. Do not dismiss them as speckles or background noise.
Output only the plain text with no markdown formatting or other commentary.
"""

DUAL_ENGINE_PAGE_PROMPT = """
You are a highly accurate OCR assistant.
Extract all text from the provided page image exactly as it appears.
CRITICAL INSTRUCTION: Pay extremely close attention to all diacritical marks (e.g. Arabic Tashkeel, French accents, German umlauts). They are deliberate and must be transcribed accurately. Do not dismiss them as speckles or background noise.
You are given a rough, error-prone draft transcription from a legacy OCR engine. Use it as a hint, but rely on the image for the final correct text, paying special attention to correcting hallucinations and diacritics in the draft.

DRAFT HINT:
{draft_text}

Output only the corrected transcribed text, without any conversational formatting or commentary.
"""

DUAL_ENGINE_CROP_PROMPT = """
You are a highly accurate OCR assistant.
Extract all text from the provided image crop exactly as it appears.
CRITICAL INSTRUCTION: Pay extremely close attention to all diacritical marks (e.g. Arabic Tashkeel, French accents, German umlauts). They are deliberate and must be transcribed accurately. Do not dismiss them as speckles or background noise.
You are given a rough draft transcription from a legacy OCR engine. Use it as a hint, but rely on the image for the final correct text.

DRAFT HINT:
{draft_text}

Output only the corrected transcribed text, without any conversational formatting or commentary.
"""

CORRECTION_PAGE_PROMPT = (
    "Attached is an image of a document and a draft transcription. The draft may contain minor "
    "errors such as missing diacritics, incorrect characters, or hallucinated words (especially in Arabic script). "
    "Carefully compare the draft to the image and output the perfectly corrected text in the same format.\n"
    "Draft Transcription:\n"
    "---\n"
    "{draft_text}\n"
    "---\n"
    "Please provide only the corrected transcription with no additional commentary."
)

CORRECTION_CROP_PROMPT = (
    "Attached is an image of a cropped text region and a draft transcription. "
    "Carefully compare the draft to the image and output the perfectly corrected text on a single line. "
    "Fix any missing diacritics or incorrect characters (especially for Arabic script). "
    "Output only the plain text with no explanation.\n"
    "Draft Transcription: {draft_text}"
)


# Handwriting-specific page prompt. The base OLMOCR_PAGE_PROMPT assumes
# printed text; this variant nudges the model to handle cursive, ascenders,
# descenders, and crossed-out words without dropping them.
HANDWRITING_PAGE_PROMPT = (
    "Attached is one page of a document that may contain HANDWRITTEN text "
    "(cursive, print, or a mix). Read it as carefully as you would a personal "
    "letter. Pay close attention to:\n"
    "  - Ascenders and descenders that may be ambiguous (b/d/p/q, n/u, etc.).\n"
    "  - Words that may be misjoined or split incorrectly across lines.\n"
    "  - Crossed-out or strikethrough words: keep them in the output as "
    "[crossed: original text].\n"
    "  - Margin annotations, arrows, and numbered notes: include them in reading order.\n"
    "Return the page as Markdown. Tables -> HTML. Equations -> LaTeX.\n"
    "Use a YAML front matter as in the printed-text prompt."
)

# Handwriting-specific crop prompt. Used when per-region OCR is requested.
HANDWRITING_CROP_PROMPT = (
    "You are recognizing a single line of HANDWRITTEN text from a document.\n"
    "Be patient with cursive, irregular spacing, and ambiguous characters.\n"
    "Pay attention to diacritics (accents, umlauts, Arabic tashkeel).\n"
    "If you cannot read the line, return an empty string rather than guess.\n"
    "Output only the plain text with no markdown formatting."
)


def select_page_prompt(handwriting_mode: bool = False) -> str:
    """Return the page-level prompt configured by the caller."""
    return HANDWRITING_PAGE_PROMPT if handwriting_mode else OLMOCR_PAGE_PROMPT


def select_crop_prompt(handwriting_mode: bool = False) -> str:
    """Return the crop-level prompt configured by the caller."""
    return HANDWRITING_CROP_PROMPT if handwriting_mode else CROP_PROMPT


def fill_dual_engine_page(draft_text: str) -> str:
    """Substitute the Tesseract draft into the dual-engine page prompt."""
    return DUAL_ENGINE_PAGE_PROMPT.replace("{draft_text}", draft_text)


def fill_dual_engine_crop(draft_text: str) -> str:
    """Substitute the Tesseract draft into the dual-engine crop prompt."""
    return DUAL_ENGINE_CROP_PROMPT.replace("{draft_text}", draft_text)


def fill_correction_page(draft_text: str) -> str:
    """Substitute the draft text into the correction page prompt."""
    return CORRECTION_PAGE_PROMPT.replace("{draft_text}", draft_text)


def fill_correction_crop(draft_text: str) -> str:
    """Substitute the draft text into the correction crop prompt."""
    return CORRECTION_CROP_PROMPT.replace("{draft_text}", draft_text)
