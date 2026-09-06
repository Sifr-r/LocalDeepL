# OmniScribe on Windows — the bundled binary

> **Status (2026-09-05): DEFERRED to v0.3+.** v0.2.0 ships the **source
> install** path (12–16 steps) as the supported end-user install. The
> single-binary PyInstaller bundle is **deferred** because the static
> analyzer refuses to bundle `anyio` (see
> [§"Known build issue"](#known-build-issue-anyio--pyinstaller-static-analysis)
> below). The doc below describes the intended end-user flow **once the
> bundle ships in v0.3+**; the spec, build script, and entry wrapper
> (`omniscribe_server.spec`, `scripts/build_windows.py`,
> `scripts/run_server.py`) are kept in tree so the next maintainer can
> pick the work back up. See
> [RFC 001 — End-User Install Path](../rfcs/2026-09-end-user-install.md)
> for the design discussion and the v0.3+ decision.

## What you get

`omniscribe-server-windows-x.y.z.exe` — a single-file binary that
embeds Python 3.12, FastAPI, uvicorn, surya-ocr, torch, pymupdf, and
the rest of the runtime stack. No Python install. No `uv`. No
`PATH` wrangling. You download one file, double-click it, and a
console window appears with the server log.

> **Codesigning is intentionally out of scope for v0.2.0.** SmartScreen
> will show an "Unknown publisher" warning the first time you run
> the binary. Click **More info** → **Run anyway** to proceed. The
> warning is not a malware flag; it's a side effect of not paying
> for a $200–500/year codesigning cert. The full RFC discussion is
> in `docs/rfcs/2026-09-end-user-install.md` §"Open questions."

## Install (the 3-step path)

1. **Download** `omniscribe-server-windows-x.y.z.exe` from the
   [latest GitHub release](https://github.com/Sifr-r/OmniScribe/releases/latest).
   Drop it anywhere — `Desktop\OmniScribe\` is the convention.

2. **Start LM Studio** (or your preferred OpenAI-compatible VLM
   server). Load a vision model. Start its local server on
   `http://localhost:1234/v1`. The
   [main README §Before you start](../../README.md#before-you-start)
   has the model recommendations.

3. **Run the binary.** Double-click `omniscribe-server-windows.exe`
   (or run it from a terminal). A console window appears with the
   server log. You should see, within ~5 seconds:

   ```
   omniscribe state_backend=sqlite
   INFO     Loaded application state from ...
   INFO     Uvicorn running on http://127.0.0.1:8000
   ```

   The server is now listening on `http://127.0.0.1:8000`. Visit
   `http://127.0.0.1:8000/api/health` in a browser to confirm.

4. **Run the Flutter client** (separate download from the same
   release page). The client connects to `http://127.0.0.1:8000` by
   default. Drag a PDF onto the Workstation tab; OCR runs against
   the VLM endpoint you started in step 2.

That's it. No `git clone`, no `uv sync`, no Flutter SDK, no Python
on `PATH`.

## What the binary contains

The PyInstaller onefile bundle is roughly **1.0–1.5 GB** and
includes:

- Python 3.12 runtime
- The full `omniscribe` package (server + plugin harness + 13
  plugins)
- All runtime dependencies: `torch`, `torchvision`, `surya-ocr`,
  `pymupdf`, `pydantic`, `fastapi`, `uvicorn`, `httpx`, `redis`,
  `pyspellchecker`, `python-docx`, `defusedxml`, `numpy`
- The runtime data files at `src/omniscribe/resources/` —
  `cordis.yml` (the plugin tree) and the bundled dictionaries

The first run takes ~5–10 seconds to extract the onefile archive
to a temp dir. Subsequent runs are ~1 second to start.

## What is NOT in the binary

- **A vision model.** You must bring your own. LM Studio (free,
  ~250 MB), Ollama, or any OpenAI-compatible endpoint.
- **The Flutter client.** It's a separate download. The Flutter
  build pipeline is independent of the Python one.
- **Your documents.** All state lives in `%LOCALAPPDATA%\omniscribe\`
  (or wherever `OMNISCRIBE_ARTIFACT_DIR` points). The SQLite
  state backend is the default since 2026-09-05.

## What changed from the source install

If you used to install from source with `uv sync`, the binary
behaves identically:

- Same env-var contract (`OMNISCRIBE_AUTH_TOKEN`,
  `OMNISCRIBE_STATE_BACKEND`, `LLM_API_BASE`, etc.)
- Same plugin tree, same default state backend (SQLite)
- Same security model: loopback bind is open, non-loopback bind
  requires a real `OMNISCRIBE_AUTH_TOKEN`

The only differences are packaging, not behavior. You can
interchange the binary and the source install — they read the
same `.env` and write to the same SQLite file.

## SmartScreen: how to run anyway

The first time you double-click the binary, Windows SmartScreen
shows:

> Windows protected your PC
> Microsoft Defender SmartScreen prevented an unrecognized app
> from starting. Running this app might put your PC at risk.

This is the codesigning-not-present warning. It is **not** a
malware flag. The "publisher" field is empty because the binary
isn't signed. To proceed:

1. Click **More info**.
2. Click **Run anyway** at the bottom of the dialog.

The binary will run normally. SmartScreen remembers your choice
for that exact binary on subsequent launches.

If you'd rather verify the binary before running it:

1. Right-click the `.exe` → **Properties** → **Digital Signatures**
   tab. The tab will say "This file is not digitally signed" — that's
   expected, and it confirms what you already know.
2. Or, verify the SHA-256 against the one in the GitHub release
   notes: `Get-FileHash .\omniscribe-server-windows-x.y.z.exe`.

## Troubleshooting

The full troubleshooting guide is at
[`docs/TROUBLESHOOTING.md`](../TROUBLESHOOTING.md). The
binary-specific entries:

- **"Windows protected your PC"** — see the SmartScreen section
  above. Codesigning is a v0.3.0 stretch.
- **"VCRUNTIME140.dll not found"** — install the
  [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170)
  (the bundle depends on it for `torch`'s native extensions). The
  v0.2.0 release notes will include a one-click installer link.
- **"First run is very slow"** — the onefile extract is
  ~5–10 seconds. Subsequent runs are <1 second. The Windows
  Defender real-time scan can add 30+ seconds the first time;
  the release notes will include a SmartScreen exclusion tip.
- **"Server boots, OCR returns nothing"** — see the
  [main README §Before you start](../../README.md#before-you-start).
  The binary doesn't include a vision model.
- **"`/api/health` returns 200 but OCR 503s** — same as above; the
  VLM endpoint isn't reachable from the binary. The default
  `LLM_API_BASE` is `http://localhost:1234/v1`.

## Building from source (maintainers only)

If you're the maintainer and want to build the binary yourself:

```bash
# One-time: install the dev dep that includes PyInstaller
uv sync --extra web --extra preprocessing

# Build (cold cache: ~5-10 min; warm: ~2-3 min)
make bundle

# Build + smoke test
make bundle-smoke
```

The spec lives at `omniscribe_server.spec` (repo root). The entry
wrapper at `scripts/run_server.py` is the single file PyInstaller
analyses. The build orchestration at `scripts/build_windows.py`
wraps the spec + the smoke test (boots the binary, hits
`/api/health`, kills the process). See the source for details.

### Known build issue: anyio + PyInstaller static analysis

**Status (2026-09-05): BLOCKED — binary boots Python but exits
immediately with `ModuleNotFoundError: No module named 'anyio'`
before serving any requests.** The 14 build attempts documented
in `docs/audits/2026-09-04-remediation-plan.md` and the chat
session did not crack this.

What the build produces today: a 270 MB `omniscribe-server.exe`
that runs `--help` correctly and the `--port 8000` path reaches
`from omniscribe.server import main` — but the `import anyio.abc`
inside `run_server.py` raises `ModuleNotFoundError` because the
PYZ archive has zero `anyio` entries.

What was tried (in the spec, in this order):

1. `collect_submodules("anyio")` with anyio 4.x — only sees the
   top-level package (4.x's `_lazyimport` hides submodules).
2. Explicit `hiddenimports` list with all anyio submodules — the
   analyzer tries to import each by name; the lazy proxy doesn't
   return a module file the analyzer can follow.
3. `hooks/hook-anyio.py` walking the package directory to emit
   hiddenimports — same root cause; the analyzer can't import
   the names, so they don't get bundled.
4. Downgrading to anyio 3.7.1 (``anyio>=3.7,<4`` in the `web`
   extra). The 14 submodules import cleanly in the venv Python
   with 3.7.1. PyInstaller still reports `ERROR: Hidden import
   'anyio._backends' not found` for every entry, and the
   resulting binary still has 0 anyio entries. 3.x fixes the
   lazy-import problem but the static analyzer still can't find
   the modules.
5. `collect_all("anyio")` — same result.
6. Force-importing `anyio.abc`, `anyio.streams`, etc. at the top
   of the spec — the spec evaluates fine but the resulting
   binary still ships with 0 anyio entries.
7. Force-importing the same modules at the top of
   `scripts/run_server.py` (the actual entry point the analyzer
   walks) — the binary now boots and reaches the
   `import anyio.abc` line, but the PYZ still has 0 anyio
   entries. The error changes from "anyio is not installed"
   to `ModuleNotFoundError: No module named 'anyio'`.

The pattern is consistent: PyInstaller's static analyzer reports
"not found" for modules that absolutely exist on disk and import
without error in the same Python environment. This is independent
of the anyio version.

Paths forward (not yet implemented; pick one in a follow-up
sprint):

- **Wait for upstream fix.** Track
  https://github.com/pyinstaller/pyinstaller/issues for anyio
  bundling. The maintainer should consider filing a new issue
  with the minimal reproducer in this spec + the venv state.
- **Use a different bundler.** Nuitka has had fewer anyio
  problems historically; the build script would call
  `python -m nuitka ...` instead of `python -m PyInstaller ...`.
  The spec would be replaced with a `nuitka_omniscribe.py`
  driver.
- **Ship source install only.** The 12-step install from the
  main README is the actual user-facing path for v0.2.0. The
  binary distribution was always a "nice to have" for
  non-developers; the audit's U3 finding ("the 12-step install
  is too much") is real, but the binary build has consumed more
  engineering time than it would save end users. Pivot to
  shipping better source-install docs (Phase 2's
  `TROUBLESHOOTING.md` already does most of this work) and
  defer the binary to a v0.3+ stretch.

The `omniscribe_server.spec` and `scripts/build_windows.py` are
left in the tree for the next maintainer who picks the bundle
back up. They will work the moment PyInstaller's analysis
recognises anyio; nothing on the venv side is blocking the
build beyond that.

When the build is unblocked, the smoke test in
`scripts/build_windows.py --smoke` is the gate: it must report
`/api/health -> 200` before a release tag can ship.

## FAQ

**Why is the binary 1 GB?** Torch alone is ~700 MB. Surya-OCR's
ONNX models and pymupdf's native binaries add another ~300 MB.
The bundle includes everything except your VLM and your documents.
A 1 GB download is the realistic floor for a local-OCR product
in 2026.

**Can I just run `omniscribe-server` from a terminal instead of
double-clicking?** Yes. The console window is real stdout / stderr,
so you can redirect, pipe, and daemonize as you would any other
CLI. The default config still reads `.env` from the current
working directory.

**Will the binary auto-update?** No. v0.2.0 ships the auto-update
roadmap in v0.3.0 (the in-binary version check is ~50 LOC; not
worth the code review weight for v0.2). For now, watch the
GitHub releases page.

**Where does state go?** `OMNISCRIBE_ARTIFACT_DIR` defaults to
`<binary-parent-dir>\omniscribe-data\` (next to the binary). The
SQLite state file is at `<that-dir>\omniscribe-state.db`. Override
with `OMNISCRIBE_ARTIFACT_DIR` to put it anywhere.

## See also

- [RFC 001 — End-User Install Path](../rfcs/2026-09-end-user-install.md) — the design discussion.
- [Remediation Plan §Phase 4](../audits/2026-09-04-remediation-plan.md#phase-4--end-user-install-path-26-weeks-owner--desktop--devx) — the project plan.
- [`scripts/build_windows.py`](../../scripts/build_windows.py) — the build orchestration.
- [`omniscribe_server.spec`](../../omniscribe_server.spec) — the PyInstaller spec.
- [`README.md`](../../README.md) — the product overview.

_Last updated: 2026-09-05_
