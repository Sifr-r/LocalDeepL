"""Chunked OCR runner.

Drives the OCR pipeline over a large PDF in bounded page-chunks so
processing time and memory stay manageable on very large documents
(typically >50 pages). For each chunk:

1. Write a *temporary* PDF containing only that chunk's pages.
2. Run the existing :func:`omniscribe.api.routers.ocr._run_ocr_pipeline`
   helper against the temp PDF.
3. Collect the per-page text and the per-chunk searchable-PDF output.

After every chunk we emit a ``chunk_complete`` WebSocket frame with the
chunk index, page range, accumulated text size, and an overall-percent
estimate. Per-chunk failures do not abort the whole run — the failed
pages are rolled into the existing ``X-Failed-Pages`` response header.

Finally we merge the per-chunk PDFs into the requested ``output_path``
and concatenate the per-chunk text artifacts into a single
token-bound text artifact.

The runner honors ``manager.is_cancelled(progress_target)`` between
chunks so a user-initiated cancel propagates without interrupting the
in-flight per-chunk pipeline call.

This module deliberately lives next to ``ocr_pipeline_factory.py``: it
reuses the same artifacts/text-store plumbing and only adds the
orchestration glue. No engine code is touched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from typing import cast

import fitz  # PyMuPDF — already a dependency via core.pdf.rasterizer

from omniscribe import OCRPipeline
from omniscribe.api.routers.websocket import ConnectionManagerLike
from omniscribe.api.schemas import ProcessSettings
from omniscribe.api.services.artifacts import PageText, TextArtifactHandle

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_chunk_pages() -> int:
    """Read the server-side default chunk size from env (or 25 pages)."""
    raw = os.environ.get("OMNISCRIBE_CHUNK_PAGES", "25")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 25
    return max(1, min(value, 500))


def _count_pdf_pages(path: str) -> int:
    """Total page count of a PDF using PyMuPDF."""
    with fitz.open(path) as doc:
        return int(doc.page_count)


def _split_pdf_pages(
    source_path: str,
    page_indices: list[int],
    target_path: str,
) -> None:
    """Write a new PDF containing only the given 1-indexed page numbers.

    Out-of-range indices are silently dropped (matches the engine's
    behavior of ignoring pages outside the requested range).
    """
    with fitz.open(source_path) as src:
        page_count = src.page_count
        out = fitz.open()
        try:
            for page_num in page_indices:
                if page_num < 1 or page_num > page_count:
                    continue
                out.insert_pdf(src, from_page=page_num - 1, to_page=page_num - 1)
            out.save(target_path, garbage=4, deflate=True)
        finally:
            out.close()


def _merge_pdfs(pdf_paths: list[str], target_path: str) -> None:
    """Concatenate ``pdf_paths`` (in order) into ``target_path``.

    Empty list produces an empty file (the engine overwrites it later).
    A single PDF is just copied.
    """
    if not pdf_paths:
        with open(target_path, "wb") as fh:
            fh.write(b"")
        return
    if len(pdf_paths) == 1:
        shutil.copyfile(pdf_paths[0], target_path)
        return
    merged = fitz.open()
    try:
        for path in pdf_paths:
            with fitz.open(path) as chunk:
                merged.insert_pdf(chunk)
        merged.save(target_path, garbage=4, deflate=True)
    finally:
        merged.close()


def _format_page_range(page_indices: list[int]) -> str:
    """Render a 1-indexed page list as a compact ``1-25,27`` string."""
    if not page_indices:
        return ""
    sorted_pages = sorted(set(page_indices))
    runs: list[str] = []
    start = sorted_pages[0]
    prev = start
    for page in sorted_pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        runs.append(f"{start}-{prev}" if start != prev else str(start))
        start = page
        prev = page
    runs.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(runs)


def _read_chunk_text_artifact(
    text_path: str,
    chunk_pages: list[int],
) -> tuple[dict[int, list[str]], int]:
    """Read a per-chunk text-artifact JSON file and re-map page numbers.

    Returns ``(aggregated_pages, char_count)`` where ``aggregated_pages``
    uses *real* (document-level) page numbers.
    """
    aggregated: dict[int, list[str]] = {}
    char_count = 0
    try:
        with open(text_path, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return aggregated, char_count

    for raw_key, lines in parsed.items():
        try:
            local_idx = int(raw_key)  # 1-indexed page number inside the chunk PDF
        except (TypeError, ValueError):
            continue
        # local_idx was assigned by the engine when it walked the chunk
        # PDF page-by-page. The chunk PDF's page ``i`` corresponds to
        # original document page ``chunk_pages[i-1]``.
        if 1 <= local_idx <= len(chunk_pages):
            real_page = chunk_pages[local_idx - 1]
        else:
            real_page = local_idx
        clean_lines = [line for line in lines if isinstance(line, str)]
        aggregated[real_page] = clean_lines
        char_count += sum(len(line) for line in clean_lines)

    return aggregated, char_count


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def run_ocr_in_chunks(
    *,
    settings: ProcessSettings,
    input_path: str,
    output_path: str,
    progress_target: str | None,
    manager: ConnectionManagerLike,
    chunk_size: int | None = None,
) -> tuple[
    OCRPipeline,
    TextArtifactHandle,
    TextArtifactHandle | None,
    str,
    list[int],
]:
    """Run OCR in page-chunks of size ``chunk_size``.

    Returns the same shape as ``api.routers.ocr._run_ocr_pipeline``:
    ``(pipeline, artifact_handle, metadata_handle, text_path,
    failed_pages)``. The pipeline returned is the last successful chunk's
    pipeline, used by callers that read ``last_document_result`` for
    response headers.
    """
    # Late import — see module docstring.
    from omniscribe.api.routers import state as router_state
    from omniscribe.api.routers.ocr import (
        _create_document_metadata_artifact,
        _run_ocr_pipeline,
    )

    resolved_chunk_size = chunk_size if chunk_size else _default_chunk_pages()
    resolved_chunk_size = max(1, min(int(resolved_chunk_size), 500))

    page_count = await asyncio.to_thread(_count_pdf_pages, input_path)
    if page_count <= 0:
        raise ValueError("Input PDF has no pages.")

    # If the document fits in a single chunk, run the existing single-
    # shot pipeline directly so the front end still gets a normal
    # response shape.
    if page_count <= resolved_chunk_size:
        return await _run_ocr_pipeline(
            settings=settings,
            input_path=input_path,
            output_path=output_path,
            progress_target=progress_target,
        )

    chunks: list[list[int]] = []
    for start in range(1, page_count + 1, resolved_chunk_size):
        end = min(start + resolved_chunk_size - 1, page_count)
        chunks.append(list(range(start, end + 1)))

    total_chunks = len(chunks)

    if progress_target:
        await manager.send_chunk_init(progress_target, total_chunks=total_chunks)
        await manager.send_progress(
            progress_target,
            f"Splitting into {total_chunks} chunks",
            5,
            stage="init",
        )

    last_pipeline: OCRPipeline | None = None
    aggregated_text: dict[int, list[str]] = {}
    failed_pages: list[int] = []
    chunk_pdf_paths: list[str] = []
    chunk_artifact_ids: list[tuple[str, str]] = []
    text_chars_so_far = 0

    work_dir = tempfile.mkdtemp(prefix="ocr_chunk_")
    try:
        for chunk_idx, chunk_pages in enumerate(chunks, start=1):
            if manager.is_cancelled(progress_target):
                logger.info(
                    "OCR chunked run cancelled before chunk %s/%s",
                    chunk_idx,
                    total_chunks,
                )
                failed_pages.extend(
                    page
                    for remaining_chunk in chunks[chunk_idx - 1 :]
                    for page in remaining_chunk
                )
                break

            chunk_pdf = os.path.join(work_dir, f"chunk_{chunk_idx:04d}.pdf")
            chunk_output_pdf = os.path.join(work_dir, f"out_chunk_{chunk_idx:04d}.pdf")
            await asyncio.to_thread(
                _split_pdf_pages, input_path, chunk_pages, chunk_pdf
            )

            # The split PDF is re-indexed from page 1. Restrict the engine to
            # that local range; document-level numbers are restored when the
            # text artifact is merged below.
            local_pages = list(range(1, len(chunk_pages) + 1))
            chunk_settings = settings.model_copy(
                update={"pages": _format_page_range(local_pages)}
            )

            try:
                (
                    _pipeline,
                    _chunk_artifact,
                    _meta_handle,
                    chunk_text_path,
                    _failed,
                ) = await _run_ocr_pipeline(
                    settings=chunk_settings,
                    input_path=chunk_pdf,
                    output_path=chunk_output_pdf,
                    progress_target=progress_target,
                )
            except Exception as chunk_exc:
                logger.warning(
                    "Chunk %s/%s failed; continuing. error=%s",
                    chunk_idx,
                    total_chunks,
                    chunk_exc,
                )
                failed_pages.extend(chunk_pages)
                continue

            last_pipeline = _pipeline
            chunk_pdf_paths.append(chunk_output_pdf)
            # Track the per-chunk text artifact so we can drop it after
            # the merge. The merged_handle replaces the per-chunk file
            # from the client's perspective, so leaving the per-chunk
            # entries around just bloats the in-memory store until TTL.
            chunk_artifact_ids.append(
                (_chunk_artifact.artifact_id, _chunk_artifact.token)
            )
            failed_pages.extend(_failed)

            chunk_text, chunk_chars = await asyncio.to_thread(
                _read_chunk_text_artifact, chunk_text_path, chunk_pages
            )
            aggregated_text.update(chunk_text)
            text_chars_so_far += chunk_chars

            overall = int((chunk_idx / total_chunks) * 100)
            if progress_target:
                page_range = _format_page_range(chunk_pages)
                await manager.send_chunk_complete(
                    progress_target,
                    chunk_idx=chunk_idx,
                    total_chunks=total_chunks,
                    page_range=page_range,
                    source_pages=list(chunk_pages),
                    text_chars_so_far=text_chars_so_far,
                    overall_percent=overall,
                )
                await manager.send_progress(
                    progress_target,
                    f"Chunk {chunk_idx}/{total_chunks}",
                    overall,
                    stage="ocr",
                )

        if last_pipeline is None:
            raise RuntimeError("All OCR chunks failed; nothing to merge.")

        await asyncio.to_thread(_merge_pdfs, chunk_pdf_paths, output_path)

        merged_handle = await router_state.text_artifacts.create(
            cast(PageText, aggregated_text)
        )

        metadata_handle = await _create_document_metadata_artifact(last_pipeline)

        return (
            last_pipeline,
            merged_handle,
            metadata_handle,
            merged_handle.path,
            sorted(set(failed_pages)),
        )
    finally:
        # Always clean up the per-chunk work dir AND the per-chunk text
        # artifacts. The work_dir is local to this run; the text
        # artifacts were registered in the global store, so without an
        # explicit delete they linger until the TTL expires (default 1h)
        # and bloat the in-memory cache.
        shutil.rmtree(work_dir, ignore_errors=True)
        for artifact_id, token in chunk_artifact_ids:
            try:
                await router_state.text_artifacts.delete(artifact_id, token)
            except Exception as cleanup_exc:
                logger.warning(
                    "Failed to delete per-chunk text artifact %s: %s",
                    artifact_id,
                    cleanup_exc,
                )


__all__ = ["run_ocr_in_chunks"]
