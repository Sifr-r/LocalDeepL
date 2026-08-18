"""In-process OpenAI-compatible VLM server for the e2e Playwright smoke.

The e2e job in ``.github/workflows/test.yml`` historically required a
real LM Studio / Ollama / OpenAI-compatible endpoint to actually run
the OCR pipeline (the page prompt → VLM → text layer roundtrip).
That dependency made the e2e job opt-in via ``workflow_dispatch`` —
there was no way to run it on a stock ``ubuntu-latest`` GHA runner.

F4.4 audit fix: this script is a tiny FastAPI app that speaks just
enough of the OpenAI chat-completion protocol to let ``omniscribe-server``
complete an OCR roundtrip without a real LLM. It serves two endpoints:

- ``GET  /v1/models``     — list the configured model as loaded.
- ``POST /v1/chat/completions`` — return a canned assistant message.

The response is parseable but textually trivial; the e2e is a UI smoke
test that exercises the full upload → submit → render-completion path
in the Svelte app, not a quality test of OCR accuracy. Pinning a
canned response is exactly what we want for a CI gate.

Run with::

    uv run python scripts/mock_llm_server.py --port 8001

The ``omniscribe-server`` is then started with::

    LLM_API_BASE=http://localhost:8001/v1 LLM_MODEL=mock-vlm \\
    uv run omniscribe-server --port 8000
"""

from __future__ import annotations

import argparse
import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse


def _build_app(model_id: str, canned_text: str) -> FastAPI:
    """Return a FastAPI app that fakes the two endpoints OmniScribe needs."""
    app = FastAPI()

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        # Pre-flight: ``OCRProcessor.ensure_model_loaded`` reads
        # ``data[*].id`` and looks for the configured model id
        # (case-insensitive). Returning one entry with the configured
        # id is the success path.
        return {"object": "list", "data": [{"id": model_id, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat_completions(payload: dict[str, Any]) -> JSONResponse:
        # The OCR pipeline (``multi_format_client.complete_vlm_prompt``)
        # reads ``choices[0].message.content`` as the assistant turn.
        # A non-empty string is sufficient to keep the pipeline moving.
        # We ignore the prompt body; the e2e does not assert OCR quality.
        body = {
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 0,
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": canned_text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
        # Echo the request shape minimally so any log scraper that
        # prints the response keeps a useful audit trail.
        _ = payload  # suppress linter
        return JSONResponse(content=body)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        # Convenience for the e2e job's wait-for-readiness loop.
        return {"status": "ok"}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to bind (default 8001 — keep clear of omniscribe-server's 8000).",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default 127.0.0.1 — local only; do not expose).",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("LLM_MODEL", "mock-vlm"),
        help="Model id to advertise on /v1/models (default $LLM_MODEL or 'mock-vlm').",
    )
    parser.add_argument(
        "--canned-text",
        default="OCR text",
        help="Text to return from /v1/chat/completions. The default is a "
        "minimal placeholder; the e2e does not assert OCR quality.",
    )
    args = parser.parse_args()

    app = _build_app(model_id=args.model, canned_text=args.canned_text)
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    # ``Server.run`` blocks until ``should_exit`` flips. The CI job
    # sends SIGTERM / SIGINT to the process group; uvicorn handles
    # both and exits cleanly.
    server.run()


if __name__ == "__main__":
    main()
