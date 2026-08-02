"""Service layer orchestrating voice transcription processing, artifact storage, and job tracking."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from omniscribe.api.routers import state
from omniscribe.api.routers.websocket import manager
from omniscribe.api.services.artifacts import PageText
from omniscribe.core.transcription import (
    TranscriptionResult,
    get_transcription_engine,
    validate_audio_input,
)


class TranscriptionService:
    """Orchestrates audio input validation, transcription engine execution, state storage, and progress."""

    async def transcribe_audio(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str | None = None,
        engine_type: str = "api",
        model: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
        transcription_api_key: str | None = None,
        language: str | None = None,
        prompt: str | None = None,
        temperature: float = 0.0,
        channel_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate input, execute transcription, store artifacts, and return formatted response."""
        start_time = time.monotonic()

        # Validate audio file format and size
        validate_audio_input(
            filename=filename,
            content_type=content_type,
            file_size=len(file_bytes),
        )

        if channel_id:
            await manager.send_progress(
                channel_id, "Validating audio file...", 10, "transcribe"
            )

        # Resolve credentials & endpoints
        cfg = getattr(state, "config", None)
        effective_model = (
            model
            or getattr(cfg, "transcription_model", None)
            or getattr(cfg, "model", None)
            or "whisper-1"
        )
        effective_api_base = (
            api_base
            or getattr(cfg, "transcription_api_base", None)
            or getattr(cfg, "api_base", None)
            or "https://api.openai.com/v1"
        )
        effective_api_key = (
            api_key
            or transcription_api_key
            or getattr(cfg, "transcription_api_key", None)
            or getattr(cfg, "api_key", None)
        )
        effective_engine = engine_type or getattr(cfg, "transcription_engine", "api")

        engine = get_transcription_engine(
            engine_type=effective_engine,
            model=effective_model,
            api_base=effective_api_base,
            api_key=effective_api_key,
        )

        if channel_id:
            await manager.send_progress(
                channel_id,
                f"Transcribing audio with {effective_model}...",
                30,
                "transcribe",
            )

        # Execute transcription
        result: TranscriptionResult = await engine.transcribe(
            file_bytes=file_bytes,
            filename=filename,
            language=language,
            prompt=prompt,
            temperature=temperature,
        )

        if channel_id:
            await manager.send_progress(
                channel_id, "Saving text artifacts...", 80, "transcribe"
            )

        # Save text artifact for downstream translation/export pipelines
        # Structuring as {0: [line_1, line_2]} to align with text artifact format
        lines = [s.text for s in result.segments] if result.segments else [result.text]
        pages_artifact_dict: PageText = {0: lines}

        text_handle = await state.text_artifacts.create(pages_artifact_dict)
        text_art_id = text_handle.artifact_id
        text_art_token = text_handle.token

        # Save metadata report artifact
        doc_result = result.to_document_result()
        metadata_page_dict: PageText = {
            0: [json.dumps(doc_result.pages[0].metadata if doc_result.pages else {})]
        }
        meta_handle = await state.metadata_artifacts.create(metadata_page_dict)

        metadata_art_id = meta_handle.artifact_id
        metadata_art_token = meta_handle.token

        duration_s = round(time.monotonic() - start_time, 3)

        # Record job history
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        state.job_history.record(
            job_id=job_id,
            filename=filename,
            model=effective_model,
            pipeline_mode="voice_transcription",
            pages="1",
            duration_s=duration_s,
            status="complete",
        )

        if channel_id:
            await manager.send_progress(
                channel_id, "Voice transcription complete.", 100, "transcribe"
            )

        return {
            "text": result.text,
            "language": result.language,
            "duration": result.duration,
            "text_artifact_id": text_art_id,
            "text_artifact_token": text_art_token,
            "metadata_artifact_id": metadata_art_id,
            "metadata_artifact_token": metadata_art_token,
            "job_id": job_id,
            "segments": [
                {
                    "id": s.id,
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "confidence": s.confidence,
                }
                for s in result.segments
            ],
        }
