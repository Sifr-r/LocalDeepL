"""
Local LLM PDF OCR - Package for OCR processing using local vision models.

Converts scanned PDFs into searchable documents using local vision LLMs
for text extraction and Surya for layout detection.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.1.0"

_EXPORT_MODULES = {
    "PDFHandler": "omniscribe.core.pdf",
    "OCRProcessor": "omniscribe.core.ocr",
    "HybridAligner": "omniscribe.core.aligner",
    "DocumentBlock": "omniscribe.core.document",
    "DocumentPage": "omniscribe.core.document",
    "DocumentResult": "omniscribe.core.document",
    "LocalPagePreprocessor": "omniscribe.core.preprocessing",
    "PagePreprocessingOptions": "omniscribe.core.preprocessing",
    "PagePreprocessingResult": "omniscribe.core.preprocessing",
    "DocumentProcessor": "omniscribe.core.processors",
    "DocumentProcessorRegistry": "omniscribe.core.processors",
    "LOCAL_DOCUMENT_PROCESSOR_NAMES": "omniscribe.core.processors",
    "QualityAnalysisProcessor": "omniscribe.core.processors",
    "ReadingOrderProcessor": "omniscribe.core.processors",
    "SectionAnalysisProcessor": "omniscribe.core.processors",
    "StructureAnalysisProcessor": "omniscribe.core.processors",
    "LayoutEnrichmentProcessor": "omniscribe.core.processors",
    "TableExtractionProcessor": "omniscribe.core.processors",
    "build_document_processors": "omniscribe.core.processors",
    "run_document_processors": "omniscribe.core.processors",
    "EvaluationMetrics": "omniscribe.core.evaluation",
    "evaluate_document": "omniscribe.core.evaluation",
    "OCRPipeline": "omniscribe.pipeline",
    "GroundedBlock": "omniscribe.core.grounded",
    "GroundedResponse": "omniscribe.core.grounded",
    "GroundedOCRBackend": "omniscribe.core.grounded",
    "PromptedGroundedOCR": "omniscribe.core.grounded",
    "DEFAULT_GROUNDING_PROMPT": "omniscribe.core.grounded",
    "parse_glm_layout_details": "omniscribe.core.grounded",
    "parse_page_range": "omniscribe.pipeline",
    "TranscriptionResult": "omniscribe.core.transcription",
    "TranscriptionSegment": "omniscribe.core.transcription",
    "validate_audio_input": "omniscribe.core.transcription",
    "get_transcription_engine": "omniscribe.core.transcription",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module 'omniscribe' has no attribute {name!r}")

    mod = import_module(  # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        module_name
    )
    value = getattr(mod, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *_EXPORT_MODULES])


__all__ = [
    "DEFAULT_GROUNDING_PROMPT",
    "DocumentBlock",
    "DocumentPage",
    "DocumentProcessor",
    "DocumentProcessorRegistry",
    "DocumentResult",
    "GroundedBlock",
    "GroundedOCRBackend",
    "GroundedResponse",
    "HybridAligner",
    "LocalPagePreprocessor",
    "OCRPipeline",
    "OCRProcessor",
    "PDFHandler",
    "PagePreprocessingOptions",
    "PagePreprocessingResult",
    "PromptedGroundedOCR",
    "QualityAnalysisProcessor",
    "ReadingOrderProcessor",
    "TranscriptionResult",
    "TranscriptionSegment",
    "__version__",
    "get_transcription_engine",
    "parse_glm_layout_details",
    "parse_page_range",
    "run_document_processors",
    "validate_audio_input",
]
