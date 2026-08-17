"""Live VLM integration tests.

These tests hit a real OpenAI-compatible VLM endpoint (e.g. LM Studio on localhost:1234/v1).
Marked with pytest.mark.live_llm.
"""

from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image, ImageDraw

from omniscribe.core.ocr.processor import OCRProcessor

pytestmark = pytest.mark.live_llm


@pytest.fixture
def ensure_live_endpoint() -> str:
    """Check that the live VLM endpoint is reachable and return the base URL."""
    api_base = os.getenv("LLM_API_BASE", "http://localhost:1234/v1").rstrip("/")
    models_url = f"{api_base}/models"
    try:
        import httpx

        resp = httpx.get(models_url, timeout=2.0)
        if resp.status_code != 200:
            pytest.skip(
                f"Live LLM endpoint at {models_url} returned status code {resp.status_code}"
            )
    except Exception as exc:
        pytest.skip(f"Live LLM endpoint not reachable at {models_url}: {exc}")
    return api_base


def _create_sample_crop_base64(text: str = "OmniScribe Live OCR Test") -> str:
    """Generate a clean image crop with text and return base64 PNG string."""
    img = Image.new("RGB", (300, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 25), text, fill=(0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@pytest.mark.asyncio
async def test_live_vlm_crop_ocr(ensure_live_endpoint: str):
    """Test single crop OCR against live VLM endpoint."""
    api_base = ensure_live_endpoint
    api_key = os.getenv("LLM_API_KEY", "lm-studio")
    model = os.getenv("LLM_MODEL", "allenai/olmocr-2-7b")

    processor = OCRProcessor(api_base=api_base, api_key=api_key, model=model)

    # Verify model is loaded on the endpoint
    await processor.ensure_model_loaded()

    crop_b64 = _create_sample_crop_base64("TESTING CROP OCR")
    result = await processor.perform_ocr_on_crop(crop_b64)

    assert isinstance(result, str)
    assert len(result.strip()) > 0
