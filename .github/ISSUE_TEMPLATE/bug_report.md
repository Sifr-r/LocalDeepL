---
name: Bug report
about: Something is broken and you want to report it.
title: "[bug] "
labels: ["bug", "needs-triage"]
assignees: []
---

## What happened

<!-- One paragraph. What you did, what you saw, what you expected. -->

## Repro steps

1.
2.
3.

## Environment

<!-- Fill in what you know; leave the rest blank. -->

- OmniScribe version (`uv run omniscribe-server --version` or the
  commit SHA you're on):
- OS:
- Python version (`uv run python --version`):
- Flutter version (if you ran the client; `flutter --version`):
- VLM endpoint and model (LM Studio / Ollama / cloud; model name):
- Install command (`uv sync --extra web` or full line):

## Server logs

<!-- Paste the relevant log lines here. Use a code block. Strip any
     secret values (auth tokens, API keys) before pasting. -->

```
[paste here]
```

## Screenshots / recordings

<!-- If it's a UI bug, attach a screenshot or a 10-second screen
     recording. Drag-and-drop into the issue body. -->

## Severity

<!-- Pick one. -->

- [ ] Blocker — server won't start, or core OCR/translation broken
- [ ] Major — a specific feature is unusable
- [ ] Minor — cosmetic, edge case, or a small UX papercut
- [ ] Not sure

## What I already tried

<!-- e.g. `make doctor`, `uv sync`, restart, etc. -->

## Anything else

<!-- Anything that doesn't fit above. -->
