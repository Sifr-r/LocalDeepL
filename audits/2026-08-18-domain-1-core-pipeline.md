# Domain 1 Audit Report: Core Pipeline & OCR Architecture

**Audit Date**: August 2026  
**Auditor**: Lead Core Pipeline & OCR Auditor  
**Target Domain**: Domain 1 — Core Pipeline (`src/omniscribe/core/`, `src/omniscribe/pipeline.py`, `src/omniscribe/config.py`, `src/omniscribe/evaluation.py`)  

---

## 1. Executive Summary

An exhaustive, line-by-line architectural and implementation audit of **Domain 1: Core Pipeline** was conducted. Domain 1 encompasses the foundational OCR engines, Surya layout detection and DP alignment, text recall boosters, grounded backends, document IR representations (`DocumentResult` and `DocumentTree`), document processors, PDF rasterization/embedding, OCR quality trust scoring, speech transcription, local ML engines (TrOCR, NLLB-200), and structure-preserving translation.

### Key Audit Metrics:
- **Modules Inspected**: 35+ core files across `core/`, `core/workflows/`, `core/ocr/`, `core/ocr_quality/`, `core/processors/`, `core/pdf/`, `core/grounded/`, `core/lexicon/`, `core/transcription/`.
- **Architectural Boundary Verification**: **CLEAN**. Zero imports of `fastapi`, `starlette`, or `omniscribe.api` inside `src/omniscribe/core/`. Core cleanly isolates from the API layer.
- **Total Findings**: 10
  - **CRITICAL**: 0
  - **HIGH**: 3
  - **MEDIUM**: 4
  - **LOW / INFO**: 3

---

## 2. Architecture Scorecard

| Subsystem | Modularity & Clean Architecture | Deterministic Error Handling | Type Safety & Strict Contracts | Concurrency & Resource Safety | Overall Grade |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Aligner & Recall** (`aligner.py`, `text_recall.py`, `text_layer_recall.py`) | 🟢 High | 🟢 Fail-open per page | 🟢 Strict | 🟢 Process-wide locks | **A** |
| **Workflows & Engines** (`workflows/hybrid.py`, `workflows/grounded.py`, `workflows/repair.py`) | 🟢 High | 🟢 CircuitBreaker + TaskGroup | 🟢 Strict | 🟡 Unmanaged tasks in grounded | **A-** |
| **OCR & Resilience** (`ocr/processor.py`, `ocr/resilience.py`, `ocr/multi_format_client.py`) | 🟢 High | 🟢 3-state CB machine | 🟢 Strict | 🟢 Event-loop safe client | **A** |
| **OCR Quality Trust Layer** (`ocr_quality/*`) | 🟢 High | 🟢 Orchestrator fail-open | 🟢 Strict | 🟢 Vectorized + pure fallback | **A+** |
| **Document Processors** (`processors/*`) | 🟡 Medium | 🟡 Strict contract bug (D1-01) | 🟢 Strict | 🟢 Pure CPU | **B+** |
| **PDF Handling** (`pdf/rasterizer.py`, `pdf/embedder.py`, `pdf/handler.py`) | 🟢 High | 🟢 Bounded batch streaming | 🟢 Strict | 🟡 Shared doc in threadpool | **B+** |
| **Block Tree & Exporters** (`block_tree.py`, `docx_tree_writer.py`, `html_writer.py`) | 🟡 Medium | 🔴 AttributeError in docx (D1-02) | 🟡 Incomplete type check | 🟢 Pure stream | **B-** |
| **Translation Subsystem** (`translation.py`, `translation_tree.py`, `dual_translator.py`) | 🟡 Medium | 🟢 Safe prompt boundary | 🟡 Skipped table nodes (D1-04) | 🟡 Chunker delim bug (D1-05) | **B** |
| **Lexicon & Transcription** (`lexicon/*`, `transcription/*`) | 🟢 High | 🟢 Fail-soft RAG | 🟢 Strict Protocol | 🟡 Eager pandas loads | **A-** |

---

## 3. Finding Register

| Finding ID | Severity | File & Location | Summary |
| :--- | :---: | :--- | :--- |
| **D1-01** | `HIGH` | `src/omniscribe/core/processors/base.py:186-206` | Strict aggregate count/text assertion fails when valid `MAY_DELETE` contract processors run. |
| **D1-02** | `HIGH` | `src/omniscribe/core/docx_tree_writer.py:46-56, 117-132` | `convert_tree_to_docx` raises `AttributeError` on `BlockNode(TABLE)` from `from_document_result` and duplicates rendered tables. |
| **D1-03** | `HIGH` | `src/omniscribe/core/grounded/prompted.py:446-455` | Unmanaged background `asyncio.create_task` tasks leak and continue running on cancellation or `CircuitOpenError`. |
| **D1-04** | `MEDIUM` | `src/omniscribe/core/translation_tree.py:110-141` | `translate_tree` bypasses all `TableNode` instances in `page.children`, leaving table cells untranslated. |
| **D1-05** | `MEDIUM` | `src/omniscribe/core/translation.py:512-536` | `_Chunker.add` delimiter overwrite scrambles formatting across multi-granularity (paragraph/line/word) chunk splits. |
| **D1-06** | `MEDIUM` | `src/omniscribe/core/processors/table.py:75-125, 178-195` | Dense enumeration in cell reconstruction shifts sparse columns and creates non-finite bounding boxes. |
| **D1-07** | `MEDIUM` | `src/omniscribe/core/pdf/embedder.py:539-545` | `ThreadPoolExecutor` concurrently accesses shared PyMuPDF `fitz.Document` handle, risking data races. |
| **D1-08** | `LOW` | `src/omniscribe/core/processors/reading_order.py:38` | `ReadingOrderProcessor._sort_key` unpacks `block.bbox` without checking for `None`. |
| **D1-09** | `LOW` | `src/omniscribe/core/trocr_engine.py:88`, `nllb_engine.py:109` | Deprecated `asyncio.get_event_loop()` usage instead of `asyncio.to_thread`. |
| **D1-10** | `LOW` | `src/omniscribe/core/lexicon/lancedb_store.py:251, 481` | Eager full-table `to_pandas()` load on every read query bypasses native vector search efficiency. |

---

## 4. Deep Dive Findings & Remediation

### Finding D1-01: Strict Processor Pipeline Assertion Rejects `MAY_DELETE` Contracts
- **Severity**: `HIGH`
- **Location**: [`src/omniscribe/core/processors/base.py:186-206`](file:///d:/OmniScribe/src/omniscribe/core/processors/base.py#L186-L206)
- **Impact**: Pipeline crash with `ValueError` when `strict=True` is enabled and any processor that legitimately consolidates or removes blocks (e.g. `TableExtractionProcessor`) is executed.

#### Failure Scenario
In `run_document_processors`, each processor is individually validated against its declared contract (`READ_ONLY`, `MUTATE_TEXT`, `REORDER`, `MAY_DELETE`, `ANY`). However, at lines 186-206, after executing the loop, an aggregate verification is performed:
```python
if strict:
    final_block_count = sum(len(page.blocks) for page in current.pages)
    if final_block_count != original_block_count:
        raise ValueError(
            f"strict mode failed: processor pipeline changed block count "
            f"from {original_block_count} to {final_block_count}"
        )
    final_texts = [block.text for page in current.pages for block in page.blocks]
    if sorted(final_texts) != sorted(original_texts):
        raise ValueError("strict mode failed: processor pipeline modified block texts")
```
If `TableExtractionProcessor` runs (contract `ProcessorContract.MAY_DELETE`), it merges constituent cell blocks into a structured table and prunes redundant standalone text blocks. The aggregate check ignores individual contracts and raises `ValueError`, crashing an otherwise healthy pipeline run.

#### Recommended Fix
```python
allows_deletion = any(
    getattr(p, "contract", None) in (ProcessorContract.MAY_DELETE, ProcessorContract.ANY)
    for p in processors
)
allows_text_mutation = any(
    getattr(p, "contract", None) in (ProcessorContract.MUTATE_TEXT, ProcessorContract.ANY)
    for p in processors
)

if strict:
    if not allows_deletion:
        final_block_count = sum(len(page.blocks) for page in current.pages)
        if final_block_count != original_block_count:
            raise ValueError(
                f"strict mode failed: processor pipeline changed block count "
                f"from {original_block_count} to {final_block_count}"
            )
    if not allows_text_mutation and not allows_deletion:
        final_texts = [block.text for page in current.pages for block in page.blocks]
        if sorted(final_texts) != sorted(original_texts):
            raise ValueError("strict mode failed: processor pipeline modified block texts")
```

---

### Finding D1-02: `convert_tree_to_docx` Crashes on `BlockNode(TABLE)` and Duplicates Rendered Tables
- **Severity**: `HIGH`
- **Location**: [`src/omniscribe/core/docx_tree_writer.py:35-56, 117-132`](file:///d:/OmniScribe/src/omniscribe/core/docx_tree_writer.py#L35-L56)
- **Impact**: `AttributeError: 'BlockNode' object has no attribute 'rows'` when exporting a DocumentTree created via `from_document_result`, plus duplicate table emission when `tree.tables` is populated.

#### Recommended Fix
1. Guard `_render_block` with `hasattr(node, "cells")` before attempting `_render_table`. If absent, fall back to paragraph rendering of `node.text`.
2. Track `rendered_table_ids: set[str]` in `convert_tree_to_docx` (mirroring `html_writer.py`) to prevent duplicate rendering from `tree.tables`.

---

### Finding D1-03: Unbounded Background Tasks on Cancellation/Error in `PromptedGroundedOCR`
- **Severity**: `HIGH`
- **Location**: [`src/omniscribe/core/grounded/prompted.py:446-455`](file:///d:/OmniScribe/src/omniscribe/core/grounded/prompted.py#L446-L455)
- **Impact**: In-flight VLM API calls continue running in the background after cancellation or early circuit-breaker trip, wasting LLM tokens and server resources.

#### Recommended Fix
Wrap `run_one` dispatch in a `try...finally` block that cancels all incomplete tasks on early exit or exception.

---

### Finding D1-04: `translate_tree` Bypasses `TableNode` Instances in `page.children`
- **Severity**: `MEDIUM`
- **Location**: [`src/omniscribe/core/translation_tree.py:110-141`](file:///d:/OmniScribe/src/omniscribe/core/translation_tree.py#L110-L141)
- **Impact**: Table content is excluded from tree-aware translations; tables remain untranslated in the resulting `DocumentTree`.

#### Recommended Fix
Iterate `node.cells` when `hasattr(node, "cells")` and translate cell blocks.

---

### Finding D1-05: `_Chunker.add` Delimiter Overwrite Scrambles Formatting
- **Severity**: `MEDIUM`
- **Location**: [`src/omniscribe/core/translation.py:512-536`](file:///d:/OmniScribe/src/omniscribe/core/translation.py#L512-L536)
- **Impact**: Sub-paragraph splits (lines/words) overwrite `self.current_delim`, causing paragraphs previously added to the same chunk to be joined with spaces instead of newlines.

#### Recommended Fix
Accumulate strings with their respective delimiters into the chunk parts list directly rather than sharing a single delimiter.
