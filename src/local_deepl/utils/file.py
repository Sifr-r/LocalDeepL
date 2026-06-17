from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def write_atomic(
    target_path: Path,
    data: str | Mapping[str, Any],
    prefix: str = "tmp_atomic",
) -> None:
    """Atomically write data (JSON or plain text) to a target path via a temporary file."""
    directory = target_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=prefix,
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = tmp.name
            if isinstance(data, str):
                tmp.write(data)
            else:
                json.dump(data, tmp, ensure_ascii=False, sort_keys=True)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        raise
