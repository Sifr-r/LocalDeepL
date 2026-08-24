"""Focused tests for the optional async translation dependency boundary."""

from __future__ import annotations

import os
import subprocess
import sys

from omniscribe.core.translate.config import TranslationSettings


def test_translation_base_imports_do_not_require_async_extras():
    import pytest

    pytest.importorskip("omniscribe.api")
    script = """
import asyncio
import importlib.abc
import sys

blocked = {"celery", "redis", "langgraph", "chromadb", "sentence_transformers"}

class BlockAsyncExtras(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError(f"blocked optional dependency: {fullname}")
        return None

sys.meta_path.insert(0, BlockAsyncExtras())

from omniscribe.api.tasks import process_translation_task
from omniscribe.core.translate.workflow import chunk_text, evaluate_node

assert chunk_text("hello") == ["hello"]
assert asyncio.run(evaluate_node({"source_chunk": ".", "translated_chunk": "", "attempts": 1}))["evaluation_score"] == 1.0
assert process_translation_task.__name__ == "process_translation_task"
"""
    env = os.environ.copy()
    src_path = os.path.abspath("src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else os.pathsep.join([src_path, env["PYTHONPATH"]])
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_optional_extras_split_lexicon_rag_dependencies():
    """The ``async-translation`` extra MUST stay light.

    Regression guard: future "I'll just add this here" PRs are easy
    to write; this test makes sure lancedb + sentence-transformers
    stay parked in the separate ``lexicon`` (formerly ``memory``) extra
    and don't bloat the async-translation install. See
    ``docs/lexicon-migration-spec.md`` §10 for the rename.
    """
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_bytes().decode("utf-8"))
    extras = data["project"]["optional-dependencies"]

    assert "async-translation" in extras, "async-translation extra is required"
    assert "lexicon" in extras, (
        "lexicon extra is required (it owns lancedb + sentence-transformers)"
    )

    async_deps = " ".join(extras["async-translation"])
    for heavy in ("lancedb", "sentence-transformers", "chromadb"):
        assert heavy not in async_deps, (
            f"{heavy!r} must not appear in the async-translation extra; "
            f"it belongs in the 'lexicon' extra"
        )

    lexicon_deps = " ".join(extras["lexicon"])
    for required in ("lancedb", "sentence-transformers", "pyarrow"):
        assert required in lexicon_deps, (
            f"{required!r} is missing from the 'lexicon' extra"
        )


async def test_translate_node_uses_injected_settings(monkeypatch):
    """translate_node routes through call_llm (refactor §2.2 — unify LLM dispatch).

    Pre-fix, translate_node instantiated AsyncOpenAI directly and bypassed the
    shared ``call_llm`` wrapper, so it had no retry/backoff and was a divergent
    fifth call path. After the fix it must go through ``call_llm`` like
    ``evaluate_node`` / ``api.services.ai._complete_text`` already do.
    """
    import omniscribe.core.translate.workflow as translation

    captured: dict[str, object] = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return "Bonjour"

    monkeypatch.setattr(translation, "call_llm", fake_call_llm)

    state = {
        "source_chunk": "Hello",
        "target_language": "French",
        "rag_context": [],
        "translated_chunk": "",
        "evaluation_score": 1.0,
        "feedback": "",
        "attempts": 0,
        "settings": TranslationSettings(
            api_base="https://example.test/v1",
            api_key="test-key",
            model="openai/test-model",
        ),
    }

    result = await translation.translate_node(state)  # type: ignore[arg-type]

    assert result["translated_chunk"] == "Bonjour"
    assert captured["model"] == "openai/test-model"
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["api_key"] == "test-key"
    assert captured["temperature"] == 0.3
    msgs = captured["messages"]
    assert isinstance(msgs, list) and msgs and isinstance(msgs[0], dict)
    assert "SOURCE TEXT:" in msgs[0]["content"]


async def test_translate_node_preserves_error_prefix_on_call_llm_failure(monkeypatch):
    """Refactor §2.2 — the ``[Translation Error: ...]`` prefix contract is preserved.

    ``evaluate_node`` short-circuits on the ``[Translation Error`` substring
    (line 237 of ``core/translate/workflow.py``), so a switch from ``AsyncOpenAI`` to
    ``call_llm`` must keep producing that prefix when the LLM raises.
    """
    import omniscribe.core.translate.workflow as translation

    async def boom(**_kwargs):
        raise RuntimeError("upstream gone")

    monkeypatch.setattr(translation, "call_llm", boom)

    state = {
        "source_chunk": "Hello",
        "target_language": "French",
        "rag_context": [],
        "translated_chunk": "",
        "evaluation_score": 1.0,
        "feedback": "",
        "attempts": 0,
        "settings": TranslationSettings(
            api_base="https://example.test/v1",
            api_key="test-key",
            model="openai/test-model",
        ),
    }

    result = await translation.translate_node(state)  # type: ignore[arg-type]
    translated = result["translated_chunk"]
    assert translated.startswith("[Translation Error")
    assert "upstream gone" in translated


async def test_translate_node_includes_glossary_and_memory(monkeypatch):
    """When the new optional state fields are populated, they must end up in the prompt."""
    from omniscribe.core.translate import workflow as translation_mod

    captured: dict[str, object] = {}

    async def fake_call_llm(**kwargs):
        captured["messages"] = kwargs.get("messages")
        return "translated"

    monkeypatch.setattr(translation_mod, "call_llm", fake_call_llm)

    state = {
        "source_chunk": "Bonjour le monde",
        "target_language": "English",
        "glossary_prompt_block": "GLOSSARY: Bonjour = Hello",
        "entity_memory_prompt_block": "NAMES: Paris",
        "sliding_window": "previously translated text",
    }
    out = await translation_mod.translate_node(state)
    assert out["translated_chunk"] == "translated", out
    messages = captured.get("messages")
    assert isinstance(messages, list) and messages and isinstance(messages[0], dict)
    prompt = messages[0]["content"]
    assert "GLOSSARY: Bonjour = Hello" in prompt
    assert "NAMES: Paris" in prompt
    assert "PREVIOUS CONTEXT" in prompt
    assert "previously translated text" in prompt
    assert "SOURCE TEXT" in prompt
