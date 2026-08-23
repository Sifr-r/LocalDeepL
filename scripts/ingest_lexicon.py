from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

# NB: do NOT import xml.etree.ElementTree here; it is not XXE-safe.
# Use scripts.ingest_lexicon._parse_xml for any external XML.
import requests

# Fix for Windows console unicode printing
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _parse_xml(content: str | bytes) -> Any:
    """Parse an XML string with XXE/DTD protection.

    The previous implementation used xml.etree.ElementTree.fromstring,
    which silently accepts <!DOCTYPE> declarations and external entity
    references. A malicious payload could trigger local file read,
    SSRF, or billion-laughs DoS. defusedxml.ElementTree.fromstring
    rejects these at the expat level before expansion.
    """
    import defusedxml.ElementTree as DET

    return DET.fromstring(content)


def fetch_xml_files(api_url: str) -> list[dict[str, Any]]:
    response = requests.get(api_url)
    response.raise_for_status()
    items = response.json()
    return [
        item
        for item in items
        if item["name"].endswith(".xml") and item["name"] != "__contents__.xml"
    ]


def parse_tei_xml(xml_content: str | bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    try:
        root = _parse_xml(xml_content)
    except Exception as e:
        print(f"Parse error: {e}")
        return []

    for entry in root.findall(".//entryFree"):
        orth = entry.find(".//orth")
        if orth is not None and orth.text:
            root_word = orth.text.strip()
            text_content = "".join(entry.itertext()).strip()

            if root_word and text_content:
                entry_id = entry.get("id", f"lane_root_{root_word}")
                entries.append(
                    {"root": root_word, "definition": text_content, "id": entry_id}
                )
    return entries


def ingest_lexicon(
    api_url: str,
    db_path: str | Path,
    dry_run: bool = False,
) -> None:
    print(f"Fetching XML file list from {api_url}")
    xml_files = fetch_xml_files(api_url)

    if dry_run:
        print(f"Dry run: Found {len(xml_files)} files. Only parsing the first one.")
        xml_files = xml_files[:1]

    all_entries: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for file_info in xml_files:
        print(f"Downloading {file_info['name']}...")
        resp = requests.get(file_info["download_url"])
        if resp.status_code == 200:
            entries = parse_tei_xml(resp.content)

            # Deduplicate IDs
            for e in entries:
                original_id = e["id"]
                unique_id = original_id
                counter = 1
                while unique_id in seen_ids:
                    unique_id = f"{original_id}_{counter}"
                    counter += 1
                seen_ids.add(unique_id)
                e["id"] = unique_id

            print(f"Extracted {len(entries)} entries from {file_info['name']}.")
            all_entries.extend(entries)
        else:
            print(f"Failed to download {file_info['name']}")

    if dry_run:
        print("Dry run complete. Sample entry:")
        if all_entries:
            print(all_entries[0])
        return

    print(
        f"Starting ingestion of {len(all_entries)} entries into LanceDB at {db_path}..."
    )
    from omniscribe.core.lexicon import LanceDBLexiconStore

    store = LanceDBLexiconStore(path=Path(db_path))

    glossary_entries: list[dict[str, object]] = []
    for entry in all_entries:
        glossary_entries.append(
            {
                "id": entry["id"],
                "source": entry["root"],
                "target": entry["definition"],
                "source_lang": "ara",
                "target_lang": "eng",
                "domain": "lexicon",
                "notes": "Lane's Lexicon",
            }
        )

    meta = store.save_glossary(
        name="Lane's Lexicon",
        format="tei_xml",
        entries=glossary_entries,
        source_uri=api_url,
    )
    print(
        f"Ingestion complete: glossary '{meta.name}' (id={meta.id}) "
        f"saved with {meta.entry_count} entries."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest Lane's Lexicon into a local LanceDB for RAG"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="https://api.github.com/repos/alpheios-project/lan/contents/db/lexica/ara/lan",
        help="GitHub API URL for the lexicon TEI XML files",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=os.path.join(
            os.path.dirname(__file__), "..", "omniscribe_artifacts", "lexicon.lance"
        ),
        help="Path to local LanceDB directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only download and parse the first file, do not ingest into LanceDB",
    )

    args = parser.parse_args()
    ingest_lexicon(args.api_url, args.db_path, args.dry_run)
