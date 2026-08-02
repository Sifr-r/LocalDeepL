"""Core OCR processing modules."""

from omniscribe.core.aligner import HybridAligner
from omniscribe.core.document import DocumentBlock, DocumentPage, DocumentResult
from omniscribe.core.evaluation import EvaluationMetrics, evaluate_document
from omniscribe.core.ocr import OCRProcessor
from omniscribe.core.pdf import PDFHandler
from omniscribe.core.preprocessing import (
    LocalPagePreprocessor,
    PagePreprocessingOptions,
    PagePreprocessingResult,
)
from omniscribe.core.processors import (
    LOCAL_DOCUMENT_PROCESSOR_NAMES,
    DocumentProcessor,
    DocumentProcessorRegistry,
    LayoutEnrichmentProcessor,
    QualityAnalysisProcessor,
    ReadingOrderProcessor,
    SectionAnalysisProcessor,
    StructureAnalysisProcessor,
    TableExtractionProcessor,
    build_document_processors,
    run_document_processors,
)
from omniscribe.core.transcription import (
    AudioValidationError,
    TranscriptionError,
    TranscriptionResult,
    TranscriptionSegment,
    get_transcription_engine,
    validate_audio_input,
)

__all__ = (
    "LOCAL_DOCUMENT_PROCESSOR_NAMES",
    "AudioValidationError",
    "DocumentBlock",
    "DocumentPage",
    "DocumentProcessor",
    "DocumentProcessorRegistry",
    "DocumentResult",
    "EvaluationMetrics",
    "HybridAligner",
    "LayoutEnrichmentProcessor",
    "LocalPagePreprocessor",
    "OCRProcessor",
    "PDFHandler",
    "PagePreprocessingOptions",
    "PagePreprocessingResult",
    "QualityAnalysisProcessor",
    "QualityRoutingOptions",
    "QualityRoutingPolicy",
    "ReadingOrderProcessor",
    "SectionAnalysisProcessor",
    "StructureAnalysisProcessor",
    "TableExtractionProcessor",
    "TranscriptionError",
    "TranscriptionResult",
    "TranscriptionSegment",
    "build_document_processors",
    "evaluate_document",
    "get_transcription_engine",
    "run_document_processors",
    "validate_audio_input",
)
