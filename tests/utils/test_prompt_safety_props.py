"""Property-based tests for :mod:`omniscribe.utils.prompt_safety`."""

from __future__ import annotations

import re

import pytest

from omniscribe.utils.prompt_safety import (
    DEFAULT_MAX_CHARS,
    sanitize_prompt_input,
)

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

_CONTROL_CHARS_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufeff\u200b-\u200d\u2060\u2028]"
)

_BOUNDARY_START = "--- CUSTOM INSTRUCTION START ---"
_BOUNDARY_END = "--- CUSTOM INSTRUCTION END ---"

_CONTROL_CHAR_SAMPLES = [
    "\x00",
    "\x01",
    "\x07",
    "\x0b",
    "\x0c",
    "\x1f",
    "\x7f",
    "\x85",
    "\x9f",
    "\ufeff",  # BOM
    "\u200b",  # zero-width space
    "\u200c",  # ZWNJ
    "\u200d",  # ZWJ
    "\u2060",  # word joiner
    "\u2028",  # line separator
]


@settings(max_examples=100, deadline=None)
@given(
    text=st.text(max_size=2000),
    max_chars=st.integers(min_value=0, max_value=500),
)
def test_output_length_bounded(text: str, max_chars: int) -> None:
    """Output length is strictly bounded by max_chars plus truncation marker length."""
    sanitized = sanitize_prompt_input(text, max_chars=max_chars)
    truncation_marker = " …[truncated]"
    assert len(sanitized) <= max_chars + len(truncation_marker)
    if len(sanitized) > max_chars:
        assert sanitized.endswith(truncation_marker)


@settings(max_examples=100, deadline=None)
@given(text=st.text())
def test_handles_arbitrary_unicode_without_error(text: str) -> None:
    """Arbitrary unicode strings never crash the sanitizer."""
    out = sanitize_prompt_input(text)
    assert isinstance(out, str)


@settings(max_examples=100, deadline=None)
@given(
    base=st.text(max_size=200),
    control=st.sampled_from(_CONTROL_CHAR_SAMPLES),
    prefix=st.text(max_size=50),
    suffix=st.text(max_size=50),
)
def test_strips_null_bytes_and_forbidden_control_characters(
    base: str, control: str, prefix: str, suffix: str
) -> None:
    """Null bytes and forbidden control characters are stripped from output."""
    poisoned = f"{prefix}{control}{base}{control}{suffix}"
    out = sanitize_prompt_input(poisoned)
    assert "\x00" not in out
    assert _CONTROL_CHARS_PATTERN.search(out) is None


@settings(max_examples=100, deadline=None)
@given(
    pre=st.text(max_size=100),
    marker=st.sampled_from([_BOUNDARY_START, _BOUNDARY_END]),
    post=st.text(max_size=100),
)
def test_neutralizes_injection_boundary_markers(
    pre: str, marker: str, post: str
) -> None:
    """Instruction boundary markers are escaped and never appear verbatim."""
    injection = f"{pre}{marker}{post}"
    out = sanitize_prompt_input(injection)
    assert _BOUNDARY_START not in out
    assert _BOUNDARY_END not in out


@settings(max_examples=100, deadline=None)
@given(
    lead=st.text(max_size=50),
    ws_run=st.text(alphabet=" \t", min_size=3, max_size=30),
    trail=st.text(max_size=50),
)
def test_collapses_excessive_whitespace_runs(
    lead: str, ws_run: str, trail: str
) -> None:
    """Whitespace runs of 3 or more spaces/tabs are collapsed to 2 spaces."""
    raw = f"{lead}{ws_run}{trail}"
    out = sanitize_prompt_input(raw, max_chars=DEFAULT_MAX_CHARS)
    # The output should not contain 3 consecutive spaces or tabs unless created across tokens
    assert "   " not in out
    assert "\t\t\t" not in out


@settings(max_examples=100, deadline=None)
@given(
    text=st.text(
        alphabet=st.characters(blacklist_categories=["Cc", "Cs"]), max_size=200
    )
)
def test_idempotent_on_short_inputs(text: str) -> None:
    """Sanitizing an already sanitized input within max_chars is idempotent."""
    first = sanitize_prompt_input(text, max_chars=1000)
    second = sanitize_prompt_input(first, max_chars=1000)
    assert first == second
