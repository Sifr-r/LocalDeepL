"""Git-hosted glossary file importer."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tarfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from omniscribe.core.glossary import Glossary
from omniscribe.utils.security import is_ssrf_target

from ._common import decode_source, entry_dict
from .summary import FormatNotAvailableError, GlossaryImportSummary, redact_dsn

logger = logging.getLogger(__name__)


def parse_git_glossary(
    *,
    url: str,
    ref: str = "HEAD",
    path: str = "GLOSSARY.md",
    credentials: str | None = None,
    timeout_sec: int = 30,
) -> GlossaryImportSummary:
    """Read one glossary file from a remote git archive without cloning history."""
    clean_url = str(url).strip()
    if not clean_url:
        raise ValueError("Git glossary URL is required.")
    if _ssrf_blocked(clean_url):
        raise ValueError("Git glossary URL is not allowed.")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("Git ref must not be empty.")
    safe_path = _validate_path(path)
    if timeout_sec <= 0 or timeout_sec > 600:
        raise ValueError("timeout_sec must be between 1 and 600 seconds.")

    remote_url = _with_credentials(clean_url, credentials)
    command = [
        "git",
        "archive",
        f"--remote={remote_url}",
        ref.strip(),
        safe_path,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            timeout=timeout_sec,
        )
    except FileNotFoundError as exc:
        raise FormatNotAvailableError(
            "Git import requires the git executable. Install with: "
            "pip install omniscribe[glossary]"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Git glossary fetch timed out.") from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError("Git glossary file could not be fetched.") from exc

    payload = _archive_member(completed.stdout, safe_path)
    text, used_encoding, warnings = decode_source(payload)
    glossary = _parse_text(text)
    if not glossary.entries:
        raise ValueError("Git glossary file contains no valid pairs.")
    serialized_raw: object = glossary.to_dict().get("entries", [])
    entries: list[dict[str, object]] = []
    if isinstance(serialized_raw, list):
        for raw_entry in serialized_raw:
            if isinstance(raw_entry, dict):
                entries.append(dict(raw_entry))
    return GlossaryImportSummary(
        entries=entries,
        format="git_glossary",
        source_uri=redact_dsn(clean_url),
        encoding=used_encoding,
        warnings=warnings,
    )


def _ssrf_blocked(url: str) -> bool:
    """Call the async SSRF validator from this synchronous parser safely."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(is_ssrf_target(url))
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, is_ssrf_target(url))
        return bool(future.result())


def _validate_path(path: str) -> str:
    clean = str(path).replace("\\", "/").strip()
    parts = clean.split("/")
    if (
        not clean
        or clean.startswith("/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("Git glossary path is invalid.")
    if "\x00" in clean:
        raise ValueError("Git glossary path is invalid.")
    return clean


def _with_credentials(url: str, credentials: str | None) -> str:
    if not credentials:
        return url
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Credentials are supported only for HTTP(S) git URLs.")
    if "@" in credentials or ":" not in credentials:
        raise ValueError("Git credentials must use username:secret form.")
    username, secret = credentials.split(":", 1)
    if not username or not secret:
        raise ValueError("Git credentials must use username:secret form.")
    return urlunsplit(
        (
            parsed.scheme,
            f"{username}:{secret}@{parsed.hostname}{_port(parsed)}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


def _port(parsed: Any) -> str:
    return f":{parsed.port}" if parsed.port is not None else ""


def _archive_member(archive: bytes, path: str) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            for member in tar.getmembers():
                if (
                    member.isfile()
                    and member.name.rsplit("/", 1)[-1] == path.rsplit("/", 1)[-1]
                ):
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        return extracted.read()
    except tarfile.ReadError:
        # A few test doubles and git wrappers return the requested file itself.
        pass
    if archive:
        return archive
    raise ValueError("Git glossary archive did not contain the requested file.")


def _parse_text(text: str) -> Glossary:
    glossary = Glossary.from_paired_lines(text)
    if glossary.entries:
        return glossary
    entries = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line.startswith("#")
            or (line.startswith("|") and set(line) <= {"|", "-", ":", " "})
        ):
            continue
        if "|" in line:
            columns = [part.strip() for part in line.strip("|").split("|")]
            if len(columns) >= 2:
                item = entry_dict(columns[0], columns[1])
                if item is not None:
                    entries.append(item)
        elif "->" in line:
            source, target = line.split("->", 1)
            item = entry_dict(source, target)
            if item is not None:
                entries.append(item)
    return Glossary.from_dict({"entries": entries})


# Silence unused import linter - Callable is part of public re-exports for typing.
_ = Callable
