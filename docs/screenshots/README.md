# OmniScribe — Screenshots & demo media

The audit's end-user lens (U6) called out the absence of any
screenshots, GIFs, or recordings. This directory is the convention
for those assets.

## What goes here

| File | What it shows | Source |
| --- | --- | --- |
| `workstation.png` | The Workstation screen of the Flutter client with a PDF loaded. | `client/lib/presentation/workstation/workstation_screen.dart` |
| `settings.png` | The Settings / Advanced Configuration panel. | `client/lib/presentation/settings/settings_screen.dart` |
| `drop-to-result.png` | The end-to-end flow: drop a PDF, watch OCR progress, preview the searchable result. | A 10-second screen recording; static screenshot optional. |
| `terminal-server-up.png` | `uv run omniscribe-server --port 8000` output with the SQLite state-backend banner. | Local terminal capture. |

All filenames are lowercased, hyphen-separated, no spaces. The
`docs/README.md` install section references `workstation.png` and
`drop-to-result.png` directly; if you add a new asset, update that
cross-reference too.

## Status (2026-09-05)

The directory is empty. Captures need a working installation
(`uv sync --extra web --extra preprocessing` + LM Studio + a
downloaded vision model + the Flutter client built locally). Phase
4 RFC 001 (Option A — PyInstaller bundle) will make the captures
reproducible from a single CI artifact; until then, manual capture
is the path.

## How to capture (manual, single-machine)

1. **Workstation:** start the Flutter client (`flutter run -d
   windows`). Drag a sample PDF from `examples/` onto the
   workstation. Take a screenshot when the OCR is in progress (the
   progress bar) and another when the result is ready. Save as
   `workstation.png` (resolution: at least 1280×720).

2. **Settings:** in the Flutter client, click the **Settings** tab.
   Take a screenshot showing the VLM endpoint and the Advanced
   Configuration panel. Save as `settings.png`.

3. **Drop-to-result recording:** use Windows Game Bar (Win + G) or
   OBS to record 10 seconds of "drop PDF → progress bar → result".
   Convert to GIF with `ffmpeg -i recording.mp4 -vf
   "fps=15,scale=800:-1" drop-to-result.gif`. Aim for <2 MB.

4. **Terminal-server-up:** start the server with the SQLite default
   (Phase 2.3). Take a screenshot of the terminal showing the
   `omniscribe state_backend=sqlite` log line and the `Uvicorn
   running on ...` line. Save as `terminal-server-up.png`.

## Why a convention, not captures

The captures depend on a running VLM endpoint and a built Flutter
client. Either of those takes 30+ minutes to set up on a fresh
machine (see [`../TROUBLESHOOTING.md`](../TROUBLESHOOTING.md)). The
audit persona can't run the captures themselves; the project
maintainer has to. So this directory is a landing pad: the next
maintainer who has a working install runs the four steps above
and the README's screenshots are no longer 404s.

## Out of scope for this directory

- Architecture diagrams (those go in `../ARCHITECTURE.md`).
- Tutorial videos (would need a hosting plan; out of scope until
  the binary distribution lands).
- A demo dataset for the screenshots — `examples/` already ships
  CC0 PDFs that work for the capture.

_Last updated: 2026-09-05_
