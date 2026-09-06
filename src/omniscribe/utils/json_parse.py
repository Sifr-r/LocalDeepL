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
    candidate = fenced.group(1).strip() if fenced else stripped

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    idx = 0
    n = len(stripped)
    while idx < n:
        brace_idx = stripped.find("{", idx)
        bracket_idx = stripped.find("[", idx)
        if brace_idx == -1 and bracket_idx == -1:
            break
        if brace_idx == -1:
            start = bracket_idx
        elif bracket_idx == -1:
            start = brace_idx
        else:
            start = min(brace_idx, bracket_idx)

        try:
            parsed, _end = decoder.raw_decode(stripped, idx=start)
            if isinstance(parsed, (dict, list)):
                return parsed
        except json.JSONDecodeError:
            pass
        idx = start + 1

    return None
