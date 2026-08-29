# Third-Party License Notice

OmniScribe's permissive MIT license covers the project source only.
Several runtime dependencies ship under copyleft licenses that
operators must consider before distribution. The summary below
matches what `pip show <package>` reports and what each upstream
project publishes in its own LICENSE file.

| Dependency | License | Notes |
| --- | --- | --- |
| `pymupdf` (AGPL-3.0) | AGPL-3.0 | PDF rasterization and embedded-text search. If you **distribute** OmniScribe (or a service that exposes its OCR pipeline over a network), the AGPL requires you to either (a) release the corresponding source to the recipients, or (b) buy a commercial PyMuPDF license from Artifex. OmniScribe itself does NOT trigger the AGPL source-release obligation as long as you run it on your own workstation and do not redistribute the binary. |
| `surya-ocr` (AGPL-3.0) | AGPL-3.0 | Surya layout detection + recognition. Same source-release obligation as PyMuPDF if OmniScribe is distributed. |
| `sentence-transformers` (Apache-2.0) | Apache-2.0 | Embedding model used by the lexicon-backed RAG. Permissive. |
| `lancedb` (Apache-2.0) | Apache-2.0 | Local vector store for the `lexicon` extra. Permissive. |
| `pymupdf` bundles MuPDF | AGPL-3.0 | Same as above; the `libmupdf` C shared library is what carries the AGPL. |
| `pytesseract` (Apache-2.0) | Apache-2.0 | Optional Tesseract binding for the dual-engine path. Permissive. Tesseract itself (the binary) is Apache-2.0 too. |
| `chromadb` (Apache-2.0) | Apache-2.0 | Optional, only in the deprecated `memory` extra. The `lexicon` extra uses LanceDB instead. |
| `lxml` (BSD-3-Clause) | BSD-3-Clause | XML glossary parsing. Permissive. |
| `pillow` (HPND / MIT-CMU) | HPND | Image decoding/encoding. Permissive. |
| `numpy` (BSD-3-Clause) | BSD-3-Clause | Permissive. |

## When does the AGPL matter?

The AGPL's network clause is a *distribution* trigger, not a *use*
trigger. If you:

- **Run OmniScribe on your own workstation for personal OCR**: AGPL
  source-release obligation does not apply.
- **Operate OmniScribe as a hosted SaaS that other people use**: AGPL
  source-release obligation does apply. Either (a) publish the
  service's source to the same set of users, or (b) buy a commercial
  PyMuPDF + Surya license from the respective vendors.
- **Distribute OmniScribe (binary or container) to other people**: AGPL
  source-release obligation applies. Bundle the source per AGPL §13 or
  buy a commercial license.

If the above is unclear for your situation, consult a lawyer. We are
not lawyers and this notice is not legal advice.

## How to keep this file in sync

When you add a new dependency that ships under a license other than
MIT / BSD / Apache-2.0 / HPND, append it to the table above in the
same turn that adds the dependency to `pyproject.toml`. The
`tests/scripts/test_licenses_match_imports.py` regression test (if
present in the test target) is the canonical check.
