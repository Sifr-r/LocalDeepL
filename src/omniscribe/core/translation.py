from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from omniscribe.core.llm_client import call_llm
from omniscribe.core.translation_config import (
    AsyncTranslationUnavailable,
    TranslationSettings,
)

logger = logging.getLogger(__name__)

# Resolve the ChromaDB directory once. Default lives next to the package root
# (legacy layout); override with `OMNISCRIBE_CHROMA_DB` for embedded use.
_DEFAULT_CHROMA_DB = Path(__file__).resolve().parent.parent.parent / "chroma_db"
CHROMA_COLLECTION_NAME = "lanes_lexicon"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# --- Quality thresholds ----------------------------------------------------
# Defaults for the translate/evaluate loop. The runtime values come from
# :class:`omniscribe.core.translation_config.TranslationSettings` (env-driven
# via ``OMNISCRIBE_TRANSLATION_*``); see refactor §2.8.
LEXICON_RESULT_COUNT = 3


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------
class TranslationState(TypedDict, total=False):
    source_chunk: str
    target_language: str
    rag_context: list[str]
    translated_chunk: str
    evaluation_score: float
    feedback: str
    attempts: int
    settings: TranslationSettings
    # Phase 4 additions
    glossary_prompt_block: str
    entity_memory_prompt_block: str
    sliding_window: str


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------


def _optional_dependency_message(package: str) -> str:
    return (
        f"Async translation requires optional dependency '{package}'. "
        "Install the async translation extras to enable this feature."
    )


def _chroma_db_path() -> Path:
    override = os.getenv("OMNISCRIBE_CHROMA_DB")
    return Path(override).expanduser().resolve() if override else _DEFAULT_CHROMA_DB


def _get_chroma_modules() -> tuple[Any, Any] | None:
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        return None
    return chromadb, embedding_functions


@lru_cache(maxsize=1)
def _chroma_client() -> Any | None:
    """Lazy-built persistent ChromaDB client. Cached for the process lifetime."""
    modules = _get_chroma_modules()
    if modules is None:
        return None
    chromadb, _embedding_functions = modules

    db_path = _chroma_db_path()
    if not db_path.exists():
        return None

    try:
        return chromadb.PersistentClient(path=str(db_path))
    except Exception as exc:
        logger.warning("Unable to open ChromaDB at %s: %s", db_path, exc)
        return None


@lru_cache(maxsize=1)
def _chroma_embedding_fn() -> Any | None:
    """Lazy-built sentence-transformer embedding function. Cached for lifetime."""
    modules = _get_chroma_modules()
    if modules is None:
        return None
    _chromadb, embedding_functions = modules
    try:
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL_NAME
        )
    except Exception as exc:
        logger.warning(
            "Unable to load embedding model %s: %s", EMBEDDING_MODEL_NAME, exc
        )
        return None


def get_chroma_collection() -> Any | None:
    """Return the cached ChromaDB collection, or None if unavailable."""
    client = _chroma_client()
    emb_fn = _chroma_embedding_fn()
    if client is None or emb_fn is None:
        return None
    try:
        return client.get_collection(
            name=CHROMA_COLLECTION_NAME, embedding_function=emb_fn
        )
    except Exception as exc:
        logger.warning("Unable to load translation lexicon from ChromaDB: %s", exc)
        return None


def retrieve_lexicon_context(state: TranslationState) -> dict[str, list[str]]:
    """Retrieves terminology from ChromaDB."""
    collection = get_chroma_collection()
    context: list[str] = []

    if collection:
        try:
            results = collection.query(
                query_texts=[state["source_chunk"]], n_results=LEXICON_RESULT_COUNT
            )
            if results and results.get("documents") and results["documents"][0]:
                context = results["documents"][0]
        except Exception as exc:
            logger.warning("Unable to retrieve translation lexicon context: %s", exc)

    return {"rag_context": context}


def _state_settings(state: TranslationState) -> TranslationSettings:
    settings = state.get("settings")
    if settings is None:
        return TranslationSettings.from_env()
    if not isinstance(settings, TranslationSettings):
        raise ValueError("translation state settings must be TranslationSettings")
    return settings


async def translate_node(state: TranslationState) -> dict[str, str | int]:
    """Calls the LLM to translate the chunk, using RAG context.

    Optional state fields (Phase 4 additions):

    - ``glossary_prompt_block``: a DeepL-style ``style_rules`` block built
      from a :class:`omniscribe.core.glossary.Glossary`.
    - ``entity_memory_prompt_block``: a context block listing proper nouns
      and dates from :class:`omniscribe.core.entity_memory.EntityMemory`.
    - ``sliding_window``: a tail of the previous translation, used as
      auxiliary consistency context.

    Routes the LLM call through :func:`omniscribe.core.llm_client.call_llm`
    (same dispatcher as ``evaluate_node`` and ``api.services.ai._complete_text``)
    so retry / backoff / circuit-breaker behavior stays consistent across
    every code path — see refactor §2.2. Errors are surfaced as the
    ``[Translation Error: ...]`` prefix that ``evaluate_node`` already
    short-circuits on (``str.startswith('[Translation Error')``).
    """
    settings = _state_settings(state)

    prompt_parts = [
        f"Translate the following text into {state['target_language']}.\n\n"
    ]

    if state.get("glossary_prompt_block"):
        prompt_parts.append(state["glossary_prompt_block"] + "\n\n")

    if state.get("entity_memory_prompt_block"):
        prompt_parts.append(state["entity_memory_prompt_block"] + "\n\n")

    if state.get("rag_context"):
        prompt_parts.append(
            "Use the following lexicon definitions to ensure correct terminology:\n"
        )
        prompt_parts.append("\n".join(state["rag_context"]) + "\n\n")

    if state.get("sliding_window"):
        prompt_parts.append(
            "PREVIOUS CONTEXT (do not translate again, just stay consistent):\n"
            + state["sliding_window"]
            + "\n\n"
        )

    if state.get("feedback"):
        prompt_parts.append(
            f"Previous translation had issues. Feedback: {state['feedback']}\nPlease fix these issues.\n\n"
        )

    prompt_parts.append(f"SOURCE TEXT:\n{state['source_chunk']}")
    prompt = "".join(prompt_parts)

    try:
        translated = await call_llm(
            model=settings.model,
            api_base=settings.api_base,
            api_key=settings.api_key,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        translated = f"[Translation Error: {e}]"

    return {"translated_chunk": translated, "attempts": state.get("attempts", 0) + 1}


async def evaluate_node(state: TranslationState) -> dict[str, float | str]:
    """Evaluates translation quality using the configured LLM.

    Fast paths (no LLM call):
    - Translation API failure → score 0.0 with retry feedback (or 1.0 if max attempts reached).
    - Max attempts reached → force accept 1.0 to break the loop.
    - Source has no letters or is < 5 chars → score 1.0 (deterministic, no point asking).
    - Length ratio below ``settings.min_length_ratio`` → score 0.0 (deterministic sanity check).
    - Length ratio above ``settings.max_length_ratio`` → score 0.0 (catches garbled / hallucinated output).
    - Length ratio in band AND no glossary (``rag_context`` empty) → score 1.0
      (skip the LLM eval when there are no glossary terms to verify against; see refactor §2.5).

    Real path: ask the configured LLM to score the translation 0.0-1.0 and return
    JSON ``{score, feedback, issues}``. If the LLM call fails or the response is
    unrecoverable, fall back to ``(1.0, "")`` so the graph doesn't loop forever.
    """
    settings = _state_settings(state)
    max_attempts = settings.max_attempts
    min_length_ratio = settings.min_length_ratio
    max_length_ratio = settings.max_length_ratio
    attempts = state.get("attempts", 0)

    translated = state.get("translated_chunk", "")
    if translated.startswith("[Translation Error"):
        if attempts >= max_attempts:
            return {"evaluation_score": 1.0, "feedback": "Failed after max attempts."}
        return {"evaluation_score": 0.0, "feedback": "Translation API call failed."}

    if attempts >= max_attempts:
        # Force accept after N tries to prevent infinite loops
        return {"evaluation_score": 1.0, "feedback": ""}

    source = state.get("source_chunk", "")
    has_letters = any(c.isalpha() for c in source)
    if not has_letters or len(source.strip()) < 5:
        return {"evaluation_score": 1.0, "feedback": "Looks good"}

    if len(translated) < len(source) * min_length_ratio:
        return {
            "evaluation_score": 0.0,
            "feedback": "Translation too short. Ensure you translate the entire chunk.",
        }

    # Upper bound: a translation > max_length_ratio x source length is almost
    # certainly garbled output (hallucination, repeated text, or untranslated
    # padding). Refactor §2.5 fast path — score 0.0 without an LLM call.
    if len(translated) > len(source) * max_length_ratio:
        return {
            "evaluation_score": 0.0,
            "feedback": "Translation too long. Likely garbled or padded output.",
        }

    # Accept-within-band fast path: when length is in the sane range AND there
    # is no glossary to verify against, the only thing the LLM eval can
    # meaningfully check is word-choice nuance. Skip the LLM call. Refactor §2.5.
    if not state.get("rag_context"):
        return {
            "evaluation_score": 1.0,
            "feedback": "Length ratio in normal range; no glossary terms to verify.",
        }

    # Real LLM-based evaluation. Fall back to "looks good" if the call fails
    # so a transient LLM outage doesn't trap us in a retry loop.
    try:
        score, feedback = await _llm_evaluate_translation(state)
    except Exception as exc:
        logger.warning("LLM evaluation failed; accepting as-is: %s", exc)
        return {"evaluation_score": 1.0, "feedback": ""}

    return {"evaluation_score": score, "feedback": feedback}


async def _llm_evaluate_translation(state: TranslationState) -> tuple[float, str]:
    """Run the configured LLM to score a translation and parse the JSON response.

    Returns ``(score, feedback)``. Raises on LLM error so the caller can decide
    on a fallback; JSON-parse failures are caught inside ``parse_evaluation_response``
    and converted to the same fallback pair.
    """
    settings = _state_settings(state)
    prompt = build_evaluation_prompt(
        source=state["source_chunk"],
        translation=state["translated_chunk"],
        target_language=state["target_language"],
        rag_context=list(state.get("rag_context") or []),
    )

    content = await call_llm(
        model=settings.model,
        api_base=settings.api_base,
        api_key=settings.api_key,
        temperature=0.1,
        messages=[{"role": "user", "content": prompt}],
    )

    return parse_evaluation_response(content)


def build_evaluation_prompt(
    *,
    source: str,
    translation: str,
    target_language: str,
    rag_context: list[str],
) -> str:
    """Build the prompt asking the LLM to score a translation.

    The expected response shape is a JSON object::

        {"score": <float 0.0-1.0>, "feedback": "<str>", "issues": [<str>, ...]}

    Anything else falls back to ``(1.0, "")`` in :func:`parse_evaluation_response`.
    """
    parts: list[str] = [
        "You are a translation quality evaluator. Score the translation below "
        f"into {target_language} on a 0.0-1.0 scale and explain any issues.\n",
        "SCORING RUBRIC:\n"
        "- 1.0: Faithful translation. No meaning loss. All glossary terms used correctly.\n"
        "- 0.7-0.9: Minor issues (one term missing, slight stylistic differences).\n"
        "- 0.4-0.6: Moderate issues (multiple terms missing, awkward phrasing, partial translation).\n"
        "- 0.0-0.3: Major issues (untranslated, mistranslated, missing significant content).\n",
    ]

    if rag_context:
        parts.append(
            "GLOSSARY (use these terms correctly):\n"
            + "\n".join(f"- {term}" for term in rag_context)
            + "\n"
        )

    parts.append(
        "OUTPUT FORMAT:\n"
        "Respond with a single JSON object and nothing else:\n"
        '{"score": <float 0.0-1.0>, "feedback": "<one sentence>", '
        '"issues": ["<issue>", ...]}\n\n'
        f"SOURCE:\n{source}\n\n"
        f"TRANSLATION ({target_language}):\n{translation}"
    )

    return "".join(parts)


_FENCED_JSON_RE = re.compile(r"\A```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL | re.I)


def parse_evaluation_response(content: str) -> tuple[float, str]:
    """Parse the LLM's evaluation JSON into ``(score, feedback)``.

    Tolerant of fenced blocks and embedded objects. Behavior:

    - No parseable dict at all → ``(1.0, "")`` (LLM didn't speak JSON).
    - Valid numeric score → clamp to ``[0, 1]`` and pair with feedback if any.
    - Missing or wrong-type score → ``(1.0, feedback)`` (default-accept; the
      LLM gave us partial info and we'd rather surface it than lose it).
      ``bool`` is explicitly rejected as a score even though it subclasses
      ``int`` in Python, otherwise JSON ``true`` would silently pass as 1.0.
    """
    stripped = content.strip()
    if not stripped:
        return 1.0, ""

    parsed = _extract_json_object(stripped)
    feedback = ""
    if parsed is not None:
        raw_feedback = parsed.get("feedback")
        if isinstance(raw_feedback, str):
            feedback = raw_feedback.strip()

    if parsed is None:
        return 1.0, feedback

    raw_score = parsed.get("score")
    # bool is a subclass of int — guard against it coercing to 1.0 silently.
    if (
        raw_score is not None
        and not isinstance(raw_score, bool)
        and isinstance(raw_score, (int, float))
    ):
        return max(0.0, min(1.0, float(raw_score))), feedback

    # Score missing or wrong-type → default-accept, preserve any feedback.
    return 1.0, feedback


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Find the first parseable JSON object in ``text``.

    Tries fenced code blocks first, then the raw text, then walks every ``{``
    index looking for a parseable object — same pattern as
    ``services.ai.parse_extraction_json`` but kept local to avoid cross-layer
    coupling between ``api.services`` and ``core``.
    """
    fenced = _FENCED_JSON_RE.match(text)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(text)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(text) if ch == "{"):
        try:
            parsed, _end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    return None


def should_refine(state: TranslationState) -> str:
    """Router logic for conditional edge."""
    settings = _state_settings(state)
    if state.get("evaluation_score", 1.0) < settings.acceptance_score:
        return "translate"
    return "end"


# ---------------------------------------------------------------------------
# Build the Graph
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_translation_app() -> Any:
    """Return the compiled LangGraph app, building it only when invoked."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise AsyncTranslationUnavailable(
            _optional_dependency_message("langgraph")
        ) from exc

    workflow = StateGraph(TranslationState)
    workflow.add_node("retrieve", retrieve_lexicon_context)
    workflow.add_node("translate", translate_node)
    workflow.add_node("evaluate", evaluate_node)

    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "translate")
    workflow.add_edge("translate", "evaluate")
    workflow.add_conditional_edges(
        "evaluate", should_refine, {"translate": "translate", "end": END}
    )

    return workflow.compile()


class _LazyTranslationApp:
    def invoke(self, *args: Any, **kwargs: Any) -> Any:
        return get_translation_app().invoke(*args, **kwargs)


translation_app = _LazyTranslationApp()


class _Chunker:
    """Encapsulates paragraph → line → word hierarchical chunking state."""

    def __init__(self, max_chunk_size: int):
        self.max_chunk_size = max_chunk_size
        self.chunks: list[str] = []
        self.current_chunk: list[str] = []
        self.current_len = 0
        self.current_delim = ""

    def add(self, text: str, delim: str = "") -> None:
        """Add text to current chunk; flush if exceeds max_chunk_size."""
        if not text:
            return

        est_len = self.current_len + len(text) + len(delim)
        if est_len > self.max_chunk_size and self.current_chunk:
            self._flush()

        self.current_chunk.append(text)
        self.current_len += len(text) + len(delim)
        self.current_delim = delim

    def _flush(self) -> None:
        """Flush current chunk to output."""
        if self.current_chunk:
            self.chunks.append(self.current_delim.join(self.current_chunk))
            self.current_chunk = []
            self.current_len = 0

    def finalize(self) -> list[str]:
        """Return all chunks and clear state."""
        self._flush()
        return [c for c in self.chunks if c.strip()]


def chunk_text(text: str, max_chunk_size: int = 4000) -> list[str]:
    """Splits text into chunks of maximum size, trying to preserve paragraph and sentence boundaries."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if max_chunk_size < 1:
        raise ValueError("max_chunk_size must be greater than zero")
    if not text:
        return []
    if len(text) <= max_chunk_size:
        return [text]

    chunker = _Chunker(max_chunk_size)

    # Split by paragraphs first
    for paragraph in text.split("\n\n"):
        if len(paragraph) <= max_chunk_size - 4:  # -4 for delimiter overhead
            chunker.add(paragraph, "\n\n")
        else:
            # Paragraph is too large, split by lines
            for line in paragraph.split("\n"):
                if len(line) <= max_chunk_size - 2:  # -2 for line delimiter
                    chunker.add(line, "\n")
                else:
                    # Line is too large, split by words
                    for word in line.split(" "):
                        chunker.add(word, " ")

    return chunker.finalize()


def run_translation(
    text: str,
    target_language: str = "English",
    settings: TranslationSettings | None = None,
) -> str:
    """Convenience function to run the compiled graph on a text by chunking it to prevent LLM context overflow."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not isinstance(target_language, str) or not target_language.strip():
        raise ValueError("target_language must be a non-empty string")
    if not text.strip():
        return ""

    active_settings = settings or TranslationSettings.from_env()
    chunks = chunk_text(text)
    translated_chunks: list[str] = []
    app = get_translation_app()

    for chunk in chunks:
        initial_state: TranslationState = {
            "source_chunk": chunk,
            "target_language": target_language,
            "rag_context": [],
            "translated_chunk": "",
            "evaluation_score": 1.0,
            "feedback": "",
            "attempts": 0,
            "settings": active_settings,
        }
        result = app.invoke(initial_state)
        translated = result.get("translated_chunk", "")
        if translated:
            translated_chunks.append(translated)

    return "\n\n".join(translated_chunks)
