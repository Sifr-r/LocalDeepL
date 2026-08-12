import json
import re
from typing import Any

_FENCED_JSON_RE = re.compile(r"\A```(?:json)?\s*(.*?)\s*```\s*\Z", re.DOTALL | re.I)


def extract_json(text: str) -> Any:
    """Find the first parseable JSON object or array in the text."""
    stripped = text.strip()
    if not stripped:
        return None

    fenced = _FENCED_JSON_RE.match(stripped)
    candidates = [fenced.group(1).strip()] if fenced else []
    candidates.append(stripped)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()
    for start in (i for i, ch in enumerate(stripped) if ch in "{["):
        try:
            parsed, _end = decoder.raw_decode(stripped[start:])
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            continue

    return None
