"""Tests for the chunked OCR runner (``api/services/ocr_chunked_runner.py``).

Two layers:

* **Helper tests** — exercise ``_split_pdf_pages``, ``_merge_pdfs``,
  ``_format_page_range``, ``_read_chunk_text_artifact`` directly against
  a synthetic PDF. These cover the pieces a future bug would corrupt
  most easily (page re-mapping, page-range formatting, JSON read-back).
* **End-to-end runner test** — drives ``run_ocr_in_chunks`` against a
  synthetic 60-page PDF with ``_run_ocr_pipeline`` monkeypatched to
  write canned text artifacts. Verifies the per-chunk
  ``chunk_complete`` WebSocket frames fire in order, the merged output
  PDF has the right page count, and the merged text artifact's content
  equals the in-memory concatenation of the per-chunk text in document
  order.

The runner doesn't hit LM Studio: every dependency is either real
(PyMuPDF, the local artifact store) or monkeypatched. No GPU / network
required, so the file is safe to run in the ``-m "not slow"`` lane.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pytest

pytest.importorskip("fastapi")


# ---------------------------------------------------------------------------
# Fixtures — synthetic PDF + canned text mapping
# ---------------------------------------------------------------------------


def _build_synthetic_pdf(path: Path, page_count: int) -> None:
    """Write a PDF with ``page_count`` blank pages (one image per page)."""
    doc = fitz.open()
    try:
        for _ in range(page_count):
            doc.new_page(width=72, height=72)
        doc.save(str(path), garbage=4, deflate=True)
    finally:
        doc.close()


@pytest.fixture(scope="session")
def synthetic_pdf() -> Path:
    """A 60-page PDF — forces ≥2 chunks at the default 25-page chunk size.

    F4.12 audit fix: the fixture is now ``scope="session"`` so the
    60-page PDF is built once per pytest run instead of once per
    test. With ~10 tests using the fixture, the function-scoped
    build was burning a few hundred ms of PyMuPDF + ``fitz.save``
    work on every test; the session-scoped build pays it once and
    the per-test cost drops to a copy. The path comes from the
    ``_session_tmp_path`` autouse helper below; we cannot
    ``tmp_path`` directly because it's function-scoped (and the
    parameter name ``tmp_path`` would shadow pytest's built-in).
    """
    session_tmp = PathFactory.get() / "synthetic_60.pdf"
    _build_synthetic_pdf(session_tmp, 60)
    return session_tmp


class PathFactory:
    """Helper for session-scoped fixtures that need a stable temp path.

    pytest's ``tmp_path`` is function-scoped, so a session-scoped
    fixture cannot depend on it. ``PathFactory.get()`` returns the
    session-scoped temp directory (set by the ``_session_tmp_path``
    fixture below). The class-level indirection lets us swap the
    storage strategy in a test override without changing the
    fixture signature.
    """

    _root: Path | None = None

    @classmethod
    def get(cls) -> Path:
        if cls._root is None:
            raise RuntimeError(
                "_session_tmp_path fixture must be initialised before "
                "PathFactory.get() is called"
            )
        return cls._root


@pytest.fixture(scope="session", autouse=True)
def _session_tmp_path() -> Path:
    """Initialise the session-scoped temp dir used by ``synthetic_pdf``."""
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="omniscribe-chunked-"))
    PathFactory._root = root
    return root


def _settings(chunk_pages: int | None = None) -> Any:
    """A minimal ProcessSettings for the runner tests."""
    from omniscribe.api.schemas import ProcessSettings

    base: dict[str, Any] = {
        "api_base": "http://localhost:0/v1",
        "api_key": "stub",
        "model": "stub-model",
        "pipeline_mode": "hybrid",
        "dpi": 100,
        "concurrency": 1,
        "dense_mode": "auto",
        "dense_threshold": 60,
        "pages": None,
        "refine": False,
        "max_image_dim": 256,
        "self_correction": False,
        "binarize": False,
        "dual_engine": False,
        "spellcheck": "none",
        "cross_page": False,
        "preprocess_pages": False,
        "orientation_detection": False,
        "deskew": False,
        "denoise": False,
        "normalize_contrast": False,
        "crop_cleanup": False,
        "quality_routing": False,
    }
    if chunk_pages is not None:
        base["chunk_pages"] = chunk_pages
    return ProcessSettings.model_validate(base)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_count_pdf_pages_returns_correct_count(synthetic_pdf: Path):
    from omniscribe.api.services.ocr_chunked_runner import _count_pdf_pages

    assert _count_pdf_pages(str(synthetic_pdf)) == 60


def test_split_pdf_pages_preserves_page_order(synthetic_pdf: Path, tmp_path: Path):
    from omniscribe.api.services.ocr_chunked_runner import _split_pdf_pages

    out = tmp_path / "chunk.pdf"
    _split_pdf_pages(str(synthetic_pdf), [3, 1, 2, 5], str(out))
    assert out.is_file()
    with fitz.open(str(out)) as doc:
        assert doc.page_count == 4
    # Spot-check: the chunk file is a valid PDF we can re-open.


def test_split_pdf_pages_drops_out_of_range_indices(
    synthetic_pdf: Path, tmp_path: Path
):
    """Out-of-range indices are silently dropped, mirroring engine semantics."""
    from omniscribe.api.services.ocr_chunked_runner import _split_pdf_pages

    out = tmp_path / "chunk.pdf"
    _split_pdf_pages(
        str(synthetic_pdf), [1, 999, 30, 60], str(out)
    )  # 999 is out of range
    with fitz.open(str(out)) as doc:
        assert doc.page_count == 3  # only 1, 30, 60 survive


def test_merge_pdfs_concatenates_in_order(tmp_path: Path):
    """``_merge_pdfs`` concatenates per-chunk PDFs in the order given."""
    from omniscribe.api.services.ocr_chunked_runner import _merge_pdfs

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    c = tmp_path / "merged.pdf"
    _build_synthetic_pdf(a, 3)
    _build_synthetic_pdf(b, 5)
    _merge_pdfs([str(a), str(b)], str(c))

    with fitz.open(str(c)) as doc:
        assert doc.page_count == 8  # 3 + 5


def test_merge_pdfs_with_single_input_copies(tmp_path: Path):
    """A single PDF passes through unchanged (covered branch)."""
    from omniscribe.api.services.ocr_chunked_runner import _merge_pdfs

    a = tmp_path / "a.pdf"
    c = tmp_path / "merged.pdf"
    _build_synthetic_pdf(a, 4)
    _merge_pdfs([str(a)], str(c))

    with fitz.open(str(c)) as doc:
        assert doc.page_count == 4


def test_format_page_range_compacts_runs():
    """``_format_page_range`` collapses consecutive pages into runs."""
    from omniscribe.api.services.ocr_chunked_runner import _format_page_range

    assert _format_page_range([]) == ""
    assert _format_page_range([1]) == "1"
    assert _format_page_range([1, 2, 3]) == "1-3"
    assert _format_page_range([1, 2, 4, 5, 7]) == "1-2,4-5,7"
    assert _format_page_range([5, 4, 3, 1, 2]) == "1-5"  # sorted + collapsed


def test_read_chunk_text_artifact_remaps_to_real_pages(tmp_path: Path):
    """Chunk-local page indices are re-mapped to document-level page numbers."""
    from omniscribe.api.services.ocr_chunked_runner import _read_chunk_text_artifact

    artifact = tmp_path / "chunk_text.json"
    # local page 1 = document page 26, local 2 = doc 27, local 3 = doc 28.
    artifact.write_text(
        json.dumps({"1": ["line for page 26"], "2": ["line for page 27"], "3": ["x"]}),
        encoding="utf-8",
    )
    aggregated, char_count = _read_chunk_text_artifact(
        str(artifact), chunk_pages=[26, 27, 28]
    )
    assert aggregated == {26: ["line for page 26"], 27: ["line for page 27"], 28: ["x"]}
    assert char_count == len("line for page 26") + len("line for page 27") + len("x")


def test_read_chunk_text_artifact_handles_missing_file(tmp_path: Path):
    """A missing artifact file returns an empty mapping (chunk may have failed)."""
    from omniscribe.api.services.ocr_chunked_runner import _read_chunk_text_artifact

    aggregated, char_count = _read_chunk_text_artifact(
        str(tmp_path / "no-such-file.json"), chunk_pages=[1, 2]
    )
    assert aggregated == {}
    assert char_count == 0


# ---------------------------------------------------------------------------
# End-to-end runner test
# ---------------------------------------------------------------------------


class _RecordingManager:
    """Captures every WebSocket frame the chunked runner emits."""

    def __init__(self) -> None:
        self.frames: list[tuple[str, dict[str, Any]]] = []
        self.cancelled = False

    async def send_chunk_init(self, channel, *, total_chunks: int) -> None:
        self.frames.append(("chunk_init", {"total_chunks": total_chunks}))

    async def send_chunk_complete(
        self,
        channel,
        *,
        chunk_idx: int,
        total_chunks: int,
        page_range: str,
        source_pages: list[int],
        text_chars_so_far: int,
        overall_percent: int | None = None,
    ) -> None:
        self.frames.append(
            (
                "chunk_complete",
                {
                    "chunk_idx": chunk_idx,
                    "total_chunks": total_chunks,
                    "page_range": page_range,
                    "source_pages": list(source_pages),
                    "text_chars_so_far": text_chars_so_far,
                    "overall_percent": overall_percent,
                },
            )
        )

    async def send_progress(
        self, channel, message: str, percent: int, *, stage: str = ""
    ) -> None:
        self.frames.append(
            ("progress", {"message": message, "percent": percent, "stage": stage})
        )

    def is_cancelled(self, channel) -> bool:
        return self.cancelled


def _make_chunk_pipeline_stub(synthetic_pdf: Path):
    """Build a ``_run_ocr_pipeline`` stub that mimics the real return shape.

    The stub walks the chunk PDF to figure out its page count, then writes
    the per-chunk page text via the real ``TextArtifactStore`` so the
    runner's per-chunk cleanup path (H4) has a real handle to delete.
    """

    counter: dict[str, Any] = {"calls": 0, "pages": []}

    async def stub_run_ocr_pipeline(
        *, settings, input_path, output_path, progress_target
    ):
        from omniscribe.api.routers import state as router_state

        counter["calls"] += 1
        counter["pages"].append(settings.pages)
        # Read the chunk PDF to find its actual page count.
        with fitz.open(input_path) as doc:
            chunk_pages = list(range(1, doc.page_count + 1))
        # Write a tiny output PDF mirroring the chunk pages.
        with fitz.open(input_path) as src:
            out = fitz.open()
            try:
                for page_num in chunk_pages:
                    out.insert_pdf(src, from_page=page_num - 1, to_page=page_num - 1)
                out.save(output_path, garbage=4, deflate=True)
            finally:
                out.close()
        # Build the per-chunk page text and register it as a real
        # text artifact. The runner's H4 cleanup deletes this handle
        # in its ``finally`` block, so the test exercises that path.
        chunk_idx = counter["calls"]
        pages_text = {
            local_idx: [f"chunk {chunk_idx} page {local_idx}"]
            for local_idx in chunk_pages
        }
        artifact_handle = await router_state.text_artifacts.create(pages_text)

        # Stub a pipeline-shaped object. Only ``last_document_result``
        # and ``last_failed_pages`` are exercised by callers in practice.
        class _StubPipeline:
            last_document_result = None
            last_failed_pages: list[int] = []

        return _StubPipeline(), artifact_handle, None, artifact_handle.path, []

    return stub_run_ocr_pipeline, counter


async def test_run_ocr_in_chunks_emits_one_frame_per_chunk(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """A 60-page PDF at chunk_size=25 yields 3 chunks + 3 chunk_complete frames."""
    from omniscribe.api.services import ocr_chunked_runner

    stub, calls = _make_chunk_pipeline_stub(synthetic_pdf)
    # The runner imports ``_run_ocr_pipeline`` locally from
    # ``omniscribe.api.routers.ocr`` so we patch the source module.
    monkeypatch.setattr("omniscribe.api.routers.ocr._run_ocr_pipeline", stub)

    output_pdf = tmp_path / "merged_output.pdf"
    manager = _RecordingManager()
    (
        _pipeline,
        _artifact,
        _meta_handle,
        _text_path,
        failed_pages,
    ) = await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(synthetic_pdf),
        output_path=str(output_pdf),
        progress_target="test-channel",
        manager=manager,
    )

    # 60 pages / 25 per chunk = 3 chunks.
    assert calls["calls"] == 3
    assert calls["pages"] == ["1-25", "1-25", "1-10"]
    assert failed_pages == []

    # First WS frame is the ``chunk_init`` pre-amble.
    init_frames = [f for kind, f in manager.frames if kind == "chunk_init"]
    assert init_frames == [{"total_chunks": 3}]

    # One ``chunk_complete`` per chunk, in order, with monotonic text growth.
    chunk_frames = [f for kind, f in manager.frames if kind == "chunk_complete"]
    assert len(chunk_frames) == 3
    assert [f["chunk_idx"] for f in chunk_frames] == [1, 2, 3]
    assert all(f["total_chunks"] == 3 for f in chunk_frames)
    text_lengths = [f["text_chars_so_far"] for f in chunk_frames]
    assert text_lengths == sorted(text_lengths)
    assert text_lengths[-1] > text_lengths[0]
    # The first chunk covers 1-25, the second 26-50, the third 51-60.
    assert chunk_frames[0]["source_pages"] == list(range(1, 26))
    assert chunk_frames[1]["source_pages"] == list(range(26, 51))
    assert chunk_frames[2]["source_pages"] == list(range(51, 61))
    assert chunk_frames[0]["page_range"] == "1-25"
    assert chunk_frames[1]["page_range"] == "26-50"
    assert chunk_frames[2]["page_range"] == "51-60"


async def test_run_ocr_in_chunks_merges_output_pdf_and_text(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """The merged output PDF + text artifact contain every page in order."""
    from omniscribe.api.services import ocr_chunked_runner

    stub, _calls = _make_chunk_pipeline_stub(synthetic_pdf)
    monkeypatch.setattr("omniscribe.api.routers.ocr._run_ocr_pipeline", stub)

    output_pdf = tmp_path / "merged_output.pdf"
    manager = _RecordingManager()
    (
        _pipeline,
        artifact_handle,
        _meta_handle,
        text_path,
        _failed,
    ) = await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(synthetic_pdf),
        output_path=str(output_pdf),
        progress_target=None,
        manager=manager,
    )

    # Merged PDF has the same page count as the source.
    assert output_pdf.is_file()
    with fitz.open(str(output_pdf)) as doc:
        assert doc.page_count == 60

    # Merged text artifact contains every page's text in document order.
    assert Path(text_path).is_file()
    payload = json.loads(Path(text_path).read_text(encoding="utf-8"))
    assert sorted(int(k) for k in payload) == list(range(1, 61))
    # Pages 1..25 are tagged "chunk 1", pages 26..50 "chunk 2", pages 51..60 "chunk 3".
    assert payload["1"] == ["chunk 1 page 1"]
    assert payload["25"] == ["chunk 1 page 25"]
    assert payload["26"] == ["chunk 2 page 1"]
    assert payload["50"] == ["chunk 2 page 25"]
    assert payload["51"] == ["chunk 3 page 1"]
    assert payload["60"] == ["chunk 3 page 10"]

    # Artifact handle is token-bound and points at the text file.
    assert artifact_handle.path == text_path
    assert artifact_handle.token and len(artifact_handle.token) >= 32

    # The temp workdir was cleaned up after the run.
    assert (
        not (tmp_path / "ocr_chunk_").exists()
        or list((tmp_path).glob("ocr_chunk_*")) == []
    )


async def test_run_ocr_in_chunks_small_doc_falls_through_to_single_shot(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """A doc with fewer pages than ``chunk_pages`` delegates to single-shot."""
    from omniscribe.api.services import ocr_chunked_runner

    # Build a 10-page PDF — under any reasonable chunk size.
    small_pdf = tmp_path / "small.pdf"
    _build_synthetic_pdf(small_pdf, 10)

    stub_calls = {"n": 0}

    async def stub_run_ocr_pipeline(
        *, settings, input_path, output_path, progress_target
    ):
        from omniscribe.api.routers import state as router_state

        stub_calls["n"] += 1
        # Copy the source PDF into the output path so the runner's
        # `_merge_pdfs` happy-path sees a real file.
        with fitz.open(input_path) as src:
            out = fitz.open()
            try:
                for page_num in range(1, src.page_count + 1):
                    out.insert_pdf(src, from_page=page_num - 1, to_page=page_num - 1)
                out.save(output_path, garbage=4, deflate=True)
            finally:
                out.close()
        # Register the per-chunk page text as a real text artifact so
        # the runner's H4 cleanup path has a real handle to delete.
        pages_text = {i: [f"single-shot page {i}"] for i in range(1, 11)}
        artifact_handle = await router_state.text_artifacts.create(pages_text)

        class _StubPipeline:
            last_document_result = None
            last_failed_pages = []

        return _StubPipeline(), artifact_handle, None, artifact_handle.path, []

    monkeypatch.setattr(
        "omniscribe.api.routers.ocr._run_ocr_pipeline",
        stub_run_ocr_pipeline,
    )

    output_pdf = tmp_path / "single_output.pdf"
    manager = _RecordingManager()
    await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(small_pdf),
        output_path=str(output_pdf),
        progress_target=None,
        manager=manager,
    )
    # Single-shot path: only one call to the pipeline and no chunk frames.
    assert stub_calls["n"] == 1
    assert [kind for kind, _ in manager.frames if kind == "chunk_complete"] == []


async def test_run_ocr_in_chunks_continues_after_chunk_failure(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """A failing chunk is recorded in ``failed_pages`` but doesn't abort the run."""
    from omniscribe.api.services import ocr_chunked_runner

    counter = {"calls": 0}

    async def flaky_run_ocr_pipeline(
        *, settings, input_path, output_path, progress_target
    ):
        from omniscribe.api.routers import state as router_state

        counter["calls"] += 1
        chunk_idx = counter["calls"]
        # The middle chunk raises — surrounding chunks succeed.
        if chunk_idx == 2:
            raise RuntimeError("simulated chunk failure")
        page_count = 0
        with fitz.open(input_path) as src:
            page_count = src.page_count
            out = fitz.open()
            try:
                for page_num in range(1, page_count + 1):
                    out.insert_pdf(src, from_page=page_num - 1, to_page=page_num - 1)
                out.save(output_path, garbage=4, deflate=True)
            finally:
                out.close()
        # Register the per-chunk page text as a real text artifact so
        # the runner's H4 cleanup path has a real handle to delete.
        pages_text = {
            i: [f"chunk {chunk_idx} page {i}"] for i in range(1, page_count + 1)
        }
        artifact_handle = await router_state.text_artifacts.create(pages_text)

        class _StubPipeline:
            last_document_result = None
            last_failed_pages = []

        return _StubPipeline(), artifact_handle, None, artifact_handle.path, []

    monkeypatch.setattr(
        "omniscribe.api.routers.ocr._run_ocr_pipeline",
        flaky_run_ocr_pipeline,
    )

    output_pdf = tmp_path / "merged_output.pdf"
    manager = _RecordingManager()
    (
        _pipeline,
        _artifact,
        _meta,
        _text_path,
        failed_pages,
    ) = await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(synthetic_pdf),
        output_path=str(output_pdf),
        # Pass an explicit channel so the runner actually emits
        # ``chunk_complete`` frames for the successful chunks.
        progress_target="failure-channel",
        manager=manager,
    )

    # 3 chunks attempted, only 2 succeeded.
    assert counter["calls"] == 3
    # The middle chunk's pages (26-50) are in ``failed_pages``.
    assert failed_pages == list(range(26, 51))
    # Only 2 chunk_complete frames were emitted (the failing chunk didn't).
    chunk_frames = [f for kind, f in manager.frames if kind == "chunk_complete"]
    assert [f["chunk_idx"] for f in chunk_frames] == [1, 3]
    # The merged PDF only contains the successful chunks' pages.
    assert output_pdf.is_file()
    with fitz.open(str(output_pdf)) as doc:
        assert doc.page_count == 35  # 25 + 10


async def test_run_ocr_in_chunks_honors_cancel_between_chunks(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """A cancel raised before chunk 2 stops the run cleanly."""
    from omniscribe.api.services import ocr_chunked_runner

    stub, calls = _make_chunk_pipeline_stub(synthetic_pdf)
    monkeypatch.setattr("omniscribe.api.routers.ocr._run_ocr_pipeline", stub)

    manager = _RecordingManager()

    # Flip the cancel flag once the first chunk has fired.
    original_send_chunk_complete = manager.send_chunk_complete

    async def spying_send_chunk_complete(*args, **kwargs):
        await original_send_chunk_complete(*args, **kwargs)
        manager.cancelled = True  # cancel after the first frame

    manager.send_chunk_complete = spying_send_chunk_complete  # type: ignore[assignment]

    output_pdf = tmp_path / "merged_output.pdf"
    (
        _pipeline,
        _artifact,
        _meta,
        _text_path,
        failed_pages,
    ) = await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(synthetic_pdf),
        output_path=str(output_pdf),
        progress_target="cancel-channel",
        manager=manager,
    )

    # The runner processed only the first chunk before honoring the cancel.
    assert calls["calls"] == 1
    chunk_frames = [f for kind, f in manager.frames if kind == "chunk_complete"]
    assert [f["chunk_idx"] for f in chunk_frames] == [1]
    assert failed_pages == list(range(26, 61))


async def test_run_ocr_in_chunks_drops_per_chunk_text_artifacts(
    synthetic_pdf: Path, tmp_path: Path, monkeypatch
):
    """H4: per-chunk text artifacts are deleted after the run.

    Without the H4 cleanup, every chunk would leave a 1h-TTL entry in the
    in-memory ``TextArtifactStore``, and the merged handle's id is the
    only one the client can reach via the download route. This test
    pins that invariant: only the merged artifact survives, every
    per-chunk one is gone.
    """
    from omniscribe.api.routers import state as router_state
    from omniscribe.api.services import ocr_chunked_runner
    from omniscribe.api.services.artifacts import ArtifactNotFoundError

    per_chunk_handles: list[Any] = []

    real_create = router_state.text_artifacts.create

    async def spying_create(page_text):
        handle = await real_create(page_text)
        per_chunk_handles.append(handle)
        return handle

    monkeypatch.setattr(router_state.text_artifacts, "create", spying_create)

    stub, calls = _make_chunk_pipeline_stub(synthetic_pdf)
    monkeypatch.setattr("omniscribe.api.routers.ocr._run_ocr_pipeline", stub)

    output_pdf = tmp_path / "merged_output.pdf"
    manager = _RecordingManager()
    (
        _pipeline,
        merged_handle,
        _meta,
        _text_path,
        _failed,
    ) = await ocr_chunked_runner.run_ocr_in_chunks(
        settings=_settings(chunk_pages=25),
        input_path=str(synthetic_pdf),
        output_path=str(output_pdf),
        progress_target="cleanup-channel",
        manager=manager,
    )

    # 3 chunks were attempted, so 3 per-chunk artifacts were created
    # (plus the merged handle the runner creates at the end, which is
    # not a per-chunk artifact and gets filtered out below).
    assert calls["calls"] == 3
    assert len(per_chunk_handles) == 4
    per_chunk_handles = [
        h for h in per_chunk_handles if h.artifact_id != merged_handle.artifact_id
    ]
    assert len(per_chunk_handles) == 3

    # The merged handle is still resolvable (the runner must not have
    # deleted it by mistake).
    merged_path = await router_state.text_artifacts.get(
        merged_handle.artifact_id, merged_handle.token
    )
    assert Path(merged_path).is_file()

    # Every per-chunk artifact was removed by the runner's finally block.
    for handle in per_chunk_handles:
        with pytest.raises(ArtifactNotFoundError):
            await router_state.text_artifacts.get(handle.artifact_id, handle.token)
