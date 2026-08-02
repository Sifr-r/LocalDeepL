"""Unit tests verifying security patches, QA bug fixes, and translation chunking."""

from __future__ import annotations

import asyncio
import os
import socket
from unittest.mock import patch

import pytest

from omniscribe.api.tasks import process_translation_task
from omniscribe.core.translation import chunk_text, evaluate_node
from omniscribe.utils.security import is_ssrf_target


def test_is_ssrf_target_defaults():
    # By default, ALLOW_SSRF_LOCAL is "true" in config for local development
    # But when ALLOW_SSRF_LOCAL is "false", let's verify SSRF catches local addresses
    with patch.dict(os.environ, {"ALLOW_SSRF_LOCAL": "false"}):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:

            def side_effect(host, port, *args, **kwargs):
                if host in (
                    "localhost",
                    "127.0.0.1",
                    "192.168.1.1",
                    "10.0.0.1",
                    "127.0.0.1.nip.io",
                ):
                    return [
                        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))
                    ]
                elif "openai.com" in host:
                    return [
                        (
                            socket.AF_INET,
                            socket.SOCK_STREAM,
                            6,
                            "",
                            ("104.18.3.161", 80),
                        )
                    ]
                else:
                    raise socket.gaierror(-2, "Name or service not known")

            mock_getaddrinfo.side_effect = side_effect

            assert asyncio.run(is_ssrf_target("http://localhost:1234/v1")) is True
            assert asyncio.run(is_ssrf_target("http://127.0.0.1/v1")) is True
            assert asyncio.run(is_ssrf_target("http://192.168.1.1/v1")) is True
            assert asyncio.run(is_ssrf_target("http://10.0.0.1/v1")) is True
            assert asyncio.run(is_ssrf_target("http://127.0.0.1.nip.io/v1")) is True
            # Public resources should pass cleanly
            assert asyncio.run(is_ssrf_target("http://api.openai.com/v1")) is False


def test_is_ssrf_target_allowed():
    # If ALLOW_SSRF_LOCAL is explicitly set to true
    with patch.dict(os.environ, {"ALLOW_SSRF_LOCAL": "true"}):
        assert asyncio.run(is_ssrf_target("http://localhost:1234/v1")) is False
        assert asyncio.run(is_ssrf_target("http://127.0.0.1/v1")) is False


def test_translation_chunking_preserves_size():
    # Generate text larger than 4000 characters
    long_text = "Paragraph one.\n\n" * 400
    assert len(long_text) > 4000

    chunks = chunk_text(long_text, max_chunk_size=4000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 4000
        assert chunk.strip() != ""


def test_evaluate_node_minimal_input_skips_loop():
    # Minimal punctuation-only input should not trigger loops
    punctuation_state = {
        "source_chunk": ".",
        "target_language": "English",
        "rag_context": [],
        "translated_chunk": "",
        "evaluation_score": 1.0,
        "feedback": "",
        "attempts": 1,
    }

    result = asyncio.run(evaluate_node(punctuation_state))
    assert result["evaluation_score"] == 1.0
    assert result["feedback"] == "Looks good"


def test_evaluate_node_normal_input_fails_correctly():
    # Normal input that is translated too shortly should fail evaluation
    bad_state = {
        "source_chunk": "This is a much longer sentence that deserves translation.",
        "target_language": "Spanish",
        "rag_context": [],
        "translated_chunk": "",  # Empty translation
        "evaluation_score": 1.0,
        "feedback": "",
        "attempts": 1,
    }

    result = asyncio.run(evaluate_node(bad_state))
    assert result["evaluation_score"] == 0.0
    assert "too short" in result["feedback"]


def test_celery_task_raises_value_error_on_missing_artifact():
    # Task should raise ValueError if artifact cannot be loaded
    with patch.object(process_translation_task, "update_state"):
        with pytest.raises(ValueError) as exc_info:
            process_translation_task.run("missing_doc", "token123", "French", [])
        assert "Could not load artifact" in str(exc_info.value)


def test_extract_data_robust_json_parsing():
    """`parse_extraction_json` returns {} on unrecoverable JSON, never raises."""
    from omniscribe.api.services import ai

    # Direct object — happy path
    assert ai.parse_extraction_json('{"vendor": "Acme"}') == {"vendor": "Acme"}

    # Fenced block (```json ... ```) — also happy path
    assert ai.parse_extraction_json('```json\n{"vendor": "Acme"}\n```') == {
        "vendor": "Acme"
    }

    # Embedded object in surrounding prose
    assert ai.parse_extraction_json('prefix text {"x": 1} suffix') == {"x": 1}

    # Unrecoverable garbage returns {} instead of raising
    assert ai.parse_extraction_json("not json at all, no brackets here") == {}

    # Top-level array (not a dict) is rejected gracefully
    assert ai.parse_extraction_json("[1, 2, 3]") == {}
