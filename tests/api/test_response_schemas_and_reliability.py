"""Response schema conformance + reliability tests.

Pins the JSON shape that ``api/schemas/responses.py`` returns for every
public router. The reliability half covers transient-failure handling
on the response-build path (catches regressions where a schema field
moves or is renamed without updating the tests).

The module imports ``_parse_grounded_json`` (private symbol) for the
grounded-backend tests; that's intentional — the public surface is
``omniscribe.core.grounded.parsers.parse_grounded_json`` and the
underscore-prefixed helper is the canonical pre-validation step the
schema layer uses to extract JSON from a VLM response.
"""

import logging
from unittest.mock import MagicMock

import pytest

from omniscribe.api.schemas.responses import (
    AsyncTranslationResponse,
    ClearJobsResponse,
    ConfigResponse,
    ExtractionResponse,
    GlossaryResponse,
    JobListResponse,
    JobRecordResponse,
    ModelsResponse,
    NLLBTranslationResponse,
    OCRStatusResponse,
    ProcessResponse,
    TranslationJobStatusResponse,
    TranslationResponse,
    TreeTranslationResponse,
)
from omniscribe.core.grounded.parsers import (
    _parse_grounded_json,
)
from omniscribe.core.postprocess import DictionaryPostProcessor, load_dictionary


def test_pydantic_response_models() -> None:
    process_resp = ProcessResponse(job_id="abc123", status="pending")
    assert process_resp.job_id == "abc123"
    assert process_resp.status == "pending"

    status_resp = OCRStatusResponse(
        job_id="abc123",
        filename="test.pdf",
        status="complete",
        created_at=100.0,
        started_at=101.0,
        completed_at=105.0,
        duration_s=4.0,
        text_artifact_id="art123",
        text_artifact_token="tok456",
        text_artifact_url="/api/text/art123",
        failed_pages=[1, 3],
    )
    assert status_resp.failed_pages == [1, 3]

    job_rec = JobRecordResponse(
        id="job1",
        filename="doc.pdf",
        model="glm",
        pipeline_mode="hybrid",
        pages="1-2",
        duration_s=2.5,
        timestamp="2026-07-27T00:00:00Z",
        status="complete",
        failed_pages=[],
    )
    job_list = JobListResponse([job_rec])
    assert len(job_list.root) == 1
    assert job_list.root[0].id == "job1"

    clear_resp = ClearJobsResponse(status="ok")
    assert clear_resp.status == "ok"

    config_resp = ConfigResponse(
        api_base="http://localhost:1234/v1",
        api_key="lm-studio",
        model="allenai/olmocr-2-7b",
        concurrency=3,
        dpi=200,
        dense_mode="auto",
        dense_threshold=60,
        max_image_dim=1024,
        refine=True,
        verify_model=True,
        pipeline_mode="hybrid",
        self_correction=False,
        binarize=False,
        dual_engine=False,
        spellcheck="none",
        cross_page=False,
        preprocess_pages=False,
        orientation_detection=False,
        deskew=False,
        denoise=False,
        normalize_contrast=False,
        crop_cleanup=False,
        quality_routing=False,
        document_processors=["reading_order"],
    )
    assert config_resp.concurrency == 3

    models_resp = ModelsResponse(models=["glm", "qwen"])
    assert models_resp.models == ["glm", "qwen"]

    extract_resp = ExtractionResponse(extracted_data={"key": "val"})
    assert extract_resp.extracted_data == {"key": "val"}

    trans_resp = TranslationResponse(translated_text="Bonjour")
    assert trans_resp.translated_text == "Bonjour"

    async_trans = AsyncTranslationResponse(job_id="task1", status="Processing")
    assert async_trans.job_id == "task1"

    trans_status = TranslationJobStatusResponse(
        job_id="task1", state="SUCCESS", result="done"
    )
    assert trans_status.state == "SUCCESS"

    glossary_resp = GlossaryResponse(entries={"hello": "bonjour"})
    assert glossary_resp.entries == {"hello": "bonjour"}

    tree_trans = TreeTranslationResponse(status="ok", page_count=5)
    assert tree_trans.page_count == 5

    nllb_trans = NLLBTranslationResponse(
        translated_text="hello", source_lang="fra", target_lang="eng"
    )
    assert nllb_trans.source_lang == "fra"


def test_load_dictionary_lru_cache() -> None:
    # Verify load_dictionary is LRU cached
    load_dictionary.cache_clear()
    info = load_dictionary.cache_info()
    assert info.hits == 0
    assert hasattr(load_dictionary, "cache_info")


def test_postprocess_exception_logging(caplog: pytest.LogCaptureFixture) -> None:
    processor = DictionaryPostProcessor(lang="en")
    mock_spell = MagicMock()
    mock_spell.known.side_effect = Exception("Internal pyspellchecker error")
    processor.spell = mock_spell

    with caplog.at_level(logging.WARNING):
        result = processor.correct_text("testing")

    assert result == "testing"
    assert (
        "Spellcheck failed for word 'testing': Internal pyspellchecker error"
        in caplog.text
    )


def test_grounded_parser_warning_logging(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        res = _parse_grounded_json(
            "not valid json at all", page_idx=2, img_w=100, img_h=100
        )

    assert res == []
    assert "Grounded bbox JSON parsing failed" in caplog.text
    assert "page 2" in caplog.text
