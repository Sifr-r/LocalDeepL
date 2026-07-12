from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from local_deepl.api.schemas import ExtractionRequest, TranslationRequest, TreeTranslationRequest
from local_deepl.api.services.ai import (
    AIServiceError,
    extract_structured_data,
)
from local_deepl.api.services.ai import (
    translate_text as translate_document_text,
)
from local_deepl.api.services.security import SERVER_ERROR_MESSAGE
from local_deepl.core.translation_config import AsyncTranslationUnavailable

from .common import _stable_server_error
from .config import _config

router = APIRouter()
logger = logging.getLogger(__name__)


def _ai_error_response(exc: AIServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.public_message},
    )


@router.post("/api/translate")
async def translate_text(body: TranslationRequest):
    """Translate OCR text into the requested target language."""
    try:
        translated = await translate_document_text(body, config=_config)
    except AIServiceError as exc:
        return _ai_error_response(exc)
    except Exception:
        logger.exception("Translation request failed")
        return _stable_server_error()
    return {"translated_text": translated}


@router.post("/api/extract")
async def extract_data(body: ExtractionRequest):
    """Extract structured JSON data from OCR text."""
    try:
        extracted = await extract_structured_data(body, config=_config)
    except AIServiceError as exc:
        return _ai_error_response(exc)
    except Exception:
        logger.exception("Extraction request failed")
        return _stable_server_error()
    return {"extracted_data": extracted}


@router.post("/api/translate/async")
async def translate_text_async(body: TreeTranslationRequest):
    """Trigger a background tree translation job via Celery.

    Returns 503 if the optional async-translation extras are not installed.
    """
    from local_deepl.api.tasks import process_translation_task

    try:
        task = process_translation_task.delay(
            body.text_artifact_id,
            body.text_artifact_token,
            body.target_language,
            body.glossary or [],
        )
    except AsyncTranslationUnavailable as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})

    return {"job_id": task.id, "status": "Processing"}


@router.get("/api/translate/status/{job_id}")
async def get_translation_status(job_id: str):
    """Poll the status of a Celery background translation job."""
    from local_deepl.api.celery_app import celery_app

    try:
        task = celery_app.AsyncResult(job_id)
    except AsyncTranslationUnavailable as exc:
        return JSONResponse(status_code=503, content={"error": str(exc)})

    try:
        response: dict[str, Any] = {
            "job_id": job_id,
            "state": task.state,
        }

        if task.state == "PENDING":
            response["status"] = "Pending..."
        elif task.state != "FAILURE":
            response["info"] = task.info
            if task.state == "SUCCESS":
                response["result"] = task.get()
        else:
            logger.error("Async translation task failed: %s", task.info)
            response["error"] = SERVER_ERROR_MESSAGE

        return response
    except Exception:
        logger.exception("Async translation status lookup failed")
        return _stable_server_error()
