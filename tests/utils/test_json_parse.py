"""Unit tests for extract_json utility."""

from __future__ import annotations

from omniscribe.utils.json_parse import extract_json


def test_extract_json_empty() -> None:
    assert extract_json("") is None
    assert extract_json("   \n\t  ") is None


def test_extract_json_direct_object() -> None:
    result = extract_json('{"key": "value", "num": 123}')
    assert result == {"key": "value", "num": 123}


def test_extract_json_direct_array() -> None:
    result = extract_json('[1, 2, "three"]')
    assert result == [1, 2, "three"]


def test_extract_json_fenced_markdown() -> None:
    raw = """```json
    {
        "status": "ok",
        "items": [1, 2]
    }
    ```"""
    assert extract_json(raw) == {"status": "ok", "items": [1, 2]}


def test_extract_json_fenced_without_json_tag() -> None:
    raw = """```
    {"status": "ok"}
    ```"""
    assert extract_json(raw) == {"status": "ok"}


def test_extract_json_embedded_in_text() -> None:
    raw = "Here is the model output:\n{\"score\": 0.95, \"details\": {\"a\": 1}}\nHope this helps!"
    result = extract_json(raw)
    assert result == {"score": 0.95, "details": {"a": 1}}


def test_extract_json_embedded_array_in_text() -> None:
    raw = "Leading text [\"alpha\", \"beta\"] and trailing text"
    assert extract_json(raw) == ["alpha", "beta"]


def test_extract_json_ignores_non_container_primitives() -> None:
    assert extract_json("42") is None
    assert extract_json('"just a string"') is None
    assert extract_json("true") is None


def test_extract_json_malformed() -> None:
    assert extract_json("{not valid json}") is None
    assert extract_json("Some text with {unclosed brace") is None
    assert extract_json("No braces or brackets here at all.") is None
