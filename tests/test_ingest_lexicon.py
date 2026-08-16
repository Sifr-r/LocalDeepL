"""Tests for the scripts/ingest_lexicon.py XXE hardening.

These tests assert the safe XML parser rejects DTD-bearing payloads.
They intentionally do NOT exercise the chromadb / network path — the
parse step is the security boundary, and it must reject malicious
payloads before the rest of the pipeline ever sees the bytes.
"""

from __future__ import annotations

import pytest

from scripts.ingest_lexicon import _parse_xml


def test_parse_xml_accepts_plain_xml() -> None:
    """A well-formed XML doc with no DTD parses cleanly."""
    root = _parse_xml("<root><child>hello</child></root>")
    assert root.tag == "root"
    assert root.find("child").text == "hello"


def test_parse_xml_rejects_external_entity_xxe() -> None:
    """An XXE payload that tries to read a local file is rejected."""
    payload = """<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""
    with pytest.raises(Exception) as excinfo:
        _parse_xml(payload)
    # defusedxml raises EntitiesForbidden for external-entity attacks.
    # We don't pin the exact class (defusedxml's hierarchy has shifted
    # across versions); we just assert the parse did NOT succeed.
    assert (
        "EntitiesForbidden" in type(excinfo.value).__name__
        or "NotSupportedError" in type(excinfo.value).__name__
        or "ExternalReferenceForbidden" in type(excinfo.value).__name__
    ), f"unexpected exception type: {type(excinfo.value).__name__}"


def test_parse_xml_rejects_billion_laughs_dos() -> None:
    """A billion-laughs DoS payload is rejected before expansion."""
    payload = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
  <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<lolz>&lol4;</lolz>"""
    with pytest.raises(Exception):  # noqa: B017 — see test docstring; defusedxml's exception hierarchy shifts across versions
        _parse_xml(payload)


def test_script_does_not_import_stdlib_xml_etree() -> None:
    """Hygiene: the script's source must not pull in xml.etree.ElementTree as an import statement."""
    import inspect
    import re

    from scripts import ingest_lexicon

    source = inspect.getsource(ingest_lexicon)
    assert not re.search(
        r"^\s*(import\s+xml\.etree|from\s+xml\.etree)", source, re.MULTILINE
    ), (
        "scripts/ingest_lexicon.py imports stdlib xml.etree; "
        "use defusedxml.ElementTree instead"
    )
    assert "defusedxml" in source, (
        "scripts/ingest_lexicon.py does not import defusedxml; "
        "add `import defusedxml.ElementTree as ET` (or call _parse_xml)"
    )
