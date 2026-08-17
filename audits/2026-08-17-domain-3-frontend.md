# Domain 3 Audit: Frontend

**Date:** 2026-08-17
**Auditor:** Mavis (explore subagent, deep-evidence investigation)
**Methodology:** Two passes: (1) broad grep for XSS sinks and type holes; (2) read every component plus the API client, WebSocket layer, and store modules.

## Scope
- **Files examined**: 95 (Svelte/TS/CSS/HTML/configs, plus 24 test files)
- **Lines of code reviewed**: ~4,800
- **Toolchain (verified)**: Svelte 5.20.2, TypeScript 5.7.3 with `strict: true`, Vite 8.2.1, `pdfjs-dist` 6.2.108, Vitest 3.0.6, Tailwind v4, jsdom 26
- **Note on Svelte 5**: package.json pins `^5.20.2`. All components still use Svelte 4 syntax (`export let`, `on:click`, `$:`) — works under Svelte 5's legacy mode.

## Findings

| ID | Severity | Area | File:Line | Description | Evidence | Recommendation |
|----|----------|------|-----------|-------------|----------|----------------|
| F3.1 | HIGH | A11y / ARIA | `frontend/src/lib/components/ui/ToastContainer.svelte:43` | Outer toast container has no `aria-live` wrapper. | `<div class="fixed bottom-5 right-5 z-50 …">` with no live-region attribute | Add `aria-live="polite"` on the container |
| F3.2 | HIGH | A11y / ARIA | `frontend/src/lib/components/ui/Toggle.svelte:19-54` | `<label for={id}>` wraps a `<button id={id}>`; risk of double-toggle. | Label at `:19` has `for={id}` pointing at the inner `<button id={id}>` at `:33` | Restructure with hidden checkbox |
| F3.3 | HIGH | Network / auth UX | `frontend/src/lib/api/client.ts:124-138` | Every 4xx/5xx response toasts a generic error; no 401-specific branch. | `client.ts:124-130` — any `!res.ok` calls `toastStore.pushToast('error', errorMessage)` | Add 401 branch with `authRequired` flag |
| F3.4 | MEDIUM | Memory / lifecycle | `frontend/src/lib/components/views/TranscriptionView.svelte:35-42, 73-75` | `audioUrl = URL.createObjectURL(...)` is never revoked on component unmount. | `onMount` at `:31-33`; no `onDestroy` | Add `onDestroy` cleanup |
| F3.5 | MEDIUM | Memory / lifecycle | `frontend/src/lib/stores/appStore.ts:144-148` | `toastStore.pushToast` schedules `setTimeout`; never tracked or cleared. | `:144-148` — bare `setTimeout(...)` | Maintain `Map<id, timeoutHandle>`; cancel on `removeToast` / `clearToasts` |
| F3.6 | MEDIUM | Memory / lifecycle | `frontend/src/lib/api/client.ts:99-139`, `frontend/src/lib/services/workstationService.ts:227-244` | No `AbortSignal` parameter on `fetchApi` / `fetchFile` / `pollOcrJobStatus`. | `client.ts:121` — bare `fetch(...)` | Add optional `signal?: AbortSignal` |
| F3.7 | MEDIUM | UX / 401 contract | `frontend/src/lib/api/client.ts:142-165` | `fetchFile` throws with no body for non-2xx; download failures lack server detail. | `:160-163` — error path drops body | Mirror `extractErrorMessage` from `fetchApi` |
| F3.8 | MEDIUM | UX / a11y / native dialog | `frontend/src/lib/components/views/JobHistoryView.svelte:45` | `window.confirm(...)` for "Clear all" is blocking and a11y hostile. | `:45` — bare `confirm(...)` | Replace with in-house `Modal` |
| F3.9 | MEDIUM | UX / state sync | `frontend/src/lib/components/views/TranslationView.svelte:47-50` and `frontend/src/lib/components/views/ExtractionView.svelte:20-23` | One-way `$:` sync from store to local state never clears. | Reactive block only runs on truthy values | Make binding bidirectional |
| F3.10 | MEDIUM | UX / reconnect storm guard | `frontend/src/lib/api/websocket.ts:122-134` | WebSocket reconnect caps at 5 attempts, silently gives up. | `:122` — `if (!isManualClose && retryCount < maxRetries)` | Add `onGiveUp` / `onReconnectFailed` callback |
| F3.11 | MEDIUM | Auth-failure reconnect storm | `frontend/src/lib/api/websocket.ts:117-135` | On server-side auth failure (close 1008), reconnect still scheduled. | `:117-135` — no inspection of `event.code` | Inspect close codes; do not reconnect on auth-class closes |
| F3.12 | MEDIUM | A11y / modal | `frontend/src/lib/components/workstation/WorkstationView.svelte:225-234` | "Processing document" overlay is `role="dialog"` but no focus trap, no `aria-labelledby`. | `:225-234` — bare `<div role="dialog" aria-modal="true">` | Reuse `Modal.svelte` or port the focus-trap pattern |
| F3.13 | MEDIUM | A11y / tablist | `frontend/src/lib/components/views/SettingsView.svelte:124-146` | Namespace tabs are bare buttons, no `role="tablist"`, no roving tabindex. | `:124-146` — `<button>` elements with no ARIA roles | Add full WAI-ARIA tab pattern |
| F3.14 | MEDIUM | Network / abort | `frontend/src/lib/components/views/TranslationView.svelte:43-45, 145-166` | Async-translation polling stops on fetch error, loses `asyncJobId` from UI. | `:43-45` `onDestroy(() => clearPolling())` | Mark polling as "paused, click to resume" |
| F3.15 | LOW | A11y / ARIA | `frontend/src/lib/components/ui/PipelineProgress.svelte:55-61` | `role="progressbar"` has no `aria-label` / `aria-labelledby`. | `:55-56` — no labelling | Add `aria-label` |
| F3.16 | LOW | A11y / table | `frontend/src/lib/components/views/JobHistoryView.svelte:102-112` and `frontend/src/lib/components/views/GlossaryView.svelte:183-193` | Tables lack `<caption>`. | `JobHistoryView.svelte:102` opens with no caption | Add visually-hidden `<caption class="sr-only">` |
| F3.17 | LOW | A11y / contrast | `frontend/src/app.css:65-66, 88-95` | `--color-foreground-subtle: #64748b` yields ~3.9:1 on dark surfaces; fails AA. | CSS at `app.css:65-66` (dark) and `:95-96` (light) | Bump dark subtle token to `#7d8ea3` or scope to non-text use |
| F3.18 | LOW | UX / race | `frontend/src/lib/components/workstation/UploadPanel.svelte:11-24, 47-50` | `handleFileChange` doesn't reset `input.value`; picking the same file twice fires no `change` event. | `handleFileChange` at `:11-16` | Set `event.target.value = ''` after dispatch |
| F3.19 | LOW | Network | `frontend/src/lib/api/client.ts:99-118` | `fetchFile` doesn't auto-set `Content-Type`; callers must pass it manually. | `:116-118` — auto-set only in `fetchApi` | Inline auto-Content-Type into `fetchFile` for JSON-string bodies |
| F3.20 | LOW | Network / state staleness | `frontend/src/lib/stores/websocketStore.ts:186-245` | `connect()` doesn't cancel a prior in-flight open timeout. | `:201-204` — `const timer = setTimeout(...)` is local | Stash timer on the store; clear at top of `connect()` |
| F3.21 | LOW | A11y / form labels | `frontend/src/lib/components/views/SettingsView.svelte:178-198, 262-282` | Model "combobox" pattern is two side-by-side inputs without fieldset/legend. | `:172-198` and `:256-282` | Use `<fieldset><legend>` wrapping both controls |
| F3.22 | LOW | Network / SPA nav | `frontend/src/lib/components/ui/TabRibbon.svelte:89` | Brand link is `<a href="/">` — full page reload, dumps in-memory state. | `:89` — `<a href="/" …>` | Use programmatic navigation |
| F3.23 | LOW | A11y / hidden text | `frontend/src/lib/components/workstation/WorkstationView.svelte:74-89` | `hidden={$activeTab !== 'workstation'}` is dead because the parent `{#if}` already gates mounting. | `App.svelte:75-89` — `{#if}` blocks | Drop the dead `hidden` attribute |
| F3.24 | LOW | Type / dev-only file | `frontend/src/lib/components/dev/.archived/Showcase.svelte` | The `Showcase.svelte` is in production source tree; included by tsconfig + tailwind content scan, never imported. | File at `frontend/src/lib/components/dev/.archived/Showcase.svelte:1-318` | Delete the file or move out of source tree |
| F3.25 | LOW | Type / `as any` discipline | `frontend/src/__tests__/setup.ts` and `pdfPreview.ts:215`, `PdfMiniViewer.svelte:79` | All occurrences are documented; test-only. | All `as any` / `as unknown as …` are scoped | None required; keep explicit style for PDF.js boundary |

### CRITICAL findings

**None.** The frontend has no reachable XSS sinks, no `dangerouslySetInnerHTML`-equivalent patterns, and no `href={userInput}` constructs — all interpolation is via Svelte 5's auto-escaped `{}` syntax. Auth tokens are now persisted to `sessionStorage` (not `localStorage`). Bearer tokens are never placed in URLs.

### HIGH findings (detailed writeup)

**F3.1 — Toast live region (A11y).** `ToastContainer.svelte:43` mounts a `pointer-events-none` div with no `aria-live` attribute. Toasts at `:54` are stamped with `role="status"` (info/success/warning) or `role="alert"` (error). `role="alert"` carries an implicit `aria-live="assertive"`, so error toasts are announced; `role="status"` is a polite live region only when nested inside one. The current container is not a live region, so success/info/warning toasts are silently dropped by NVDA/JAWS/VoiceOver. Mitigation: add `aria-live="polite" aria-relevant="additions"` to the wrapper. WCAG SC 4.1.3 (Status Messages) and SC 1.3.1 (Info and Relationships) are both relevant.

**F3.2 — Toggle label/button overlap (A11y / interactivity).** `Toggle.svelte:19-54` puts a `<button id={id} role="switch">` inside a `<label for={id}>`. The `<label>` is designed to associate a single form control; when the labeled control is a `<button>`, the browser re-fires the button's `click` handler on any label click. The current implementation has the button's `on:click` toggle the state, so clicking anywhere in the row toggles once. But clicking directly on the button triggers both the button's own click and the label's delegated click — depending on event-bubbling order in the browser, this can double-toggle. Replace with a hidden `<input type="checkbox" bind:checked={checked}>` and a styled `<span class="switch">`; the existing `<label>` then wraps both.

**F3.3 — 401 handling is generic (Network / auth UX).** `client.ts:124-130` always calls `toastStore.pushToast('error', errorMessage)` on `!res.ok`. There is no `status === 401` (or 403) branch. AGENTS.md says auth is opt-in via `OMNISCRIBE_AUTH_TOKEN`. When the server has that env var set, every browser request without a matching `Authorization: Bearer <token>` will toast "Request failed with status 401" (the server's `detail` string) and the user has no path to set the token without discovering the Settings tab. Mitigation: special-case 401 to set an `authRequired` flag in `appStore`, suppress repeat toasts (debounce 5 s), and surface a single banner with a deep-link to the Settings auth tab.

### MEDIUM findings (one-liner each)
- F3.4 — `URL.createObjectURL` for `audioUrl` is never revoked on component unmount; no `onDestroy`.
- F3.5 — `setTimeout` for toast TTL is untracked; `removeToast` / `clearToasts` cannot cancel it.
- F3.6 — No `AbortSignal` plumbing; in-flight fetches continue after unmount.
- F3.7 — `fetchFile` drops the response body and only shows `statusText`; download failures lack server detail.
- F3.8 — `window.confirm` used for destructive "Clear all" instead of the in-house `Modal` primitive.
- F3.9 — One-way `$:` sync from `$documentStore` to local state never clears when the store clears.
- F3.10 — WebSocket reconnect caps at 5 attempts, then silently gives up.
- F3.11 — `onclose` reconnect path doesn't inspect `event.code`; auth-class closes (1008) trigger wasteful reconnects.
- F3.12 — "Processing document" overlay is `role="dialog" aria-modal="true"` but lacks focus trap, labelledby, focus restoration.
- F3.13 — Namespace tabs are plain buttons; no WAI-ARIA tablist pattern (regression vs. `TabRibbon`).
- F3.14 — Async-translation polling stops on fetch error and loses `asyncJobId` from the UI; no resume path.

### LOW findings (one-liner each)
- F3.15 — `role="progressbar"` has no `aria-label` / `aria-labelledby`.
- F3.16 — `<table>` elements lack `<caption>`.
- F3.17 — `--color-foreground-subtle` (#64748b) yields ~3.9:1 contrast on dark surfaces; fails AA.
- F3.18 — `handleFileChange` never resets `input.value`; re-picking the same file fires no `change` event.
- F3.19 — `fetchFile` doesn't auto-set `Content-Type` for JSON-string bodies.
- F3.20 — Overlapping `connect()` calls do not cancel prior OPEN_TIMEOUT timers.
- F3.21 — OCR/Translation model free-text input + Select pair lack a `<fieldset><legend>` grouping.
- F3.22 — Brand `<a href="/">` triggers a full page reload, blowing away in-memory state.
- F3.23 — `hidden={$activeTab !== '…'}` is dead because the parent `{#if}` already gates mounting.
- F3.24 — Dev-only `Showcase.svelte` in production source tree; included by tsconfig + tailwind content scan.
- F3.25 — `as any` / `as unknown as …` usage is appropriately scoped (test setup, two PDF.js bridge casts).

## Cross-cutting observations

- **Auth is sound but UX-orphaned.** The token is in `sessionStorage`; `Authorization: Bearer` is attached per route family in `client.ts:49-56`. The failure path (F3.3) gives the user no in-app way to discover the Settings auth tab.
- **Cancel/cleanup contract is patchy.** `classifyOcrFailure` handles 503 + `cancelled: true` specially. The async OCR submission has a cancel endpoint, the sync `POST /api/process` path has no abortable cancel.
- **Polling: backend-facing contract, frontend-FSM.** Translation polling uses `state === 'SUCCESS'` (Celery), OCR polling uses `status.status === 'complete'` (custom). Cross-domain consistency: two different state-machine vocabularies.
- **Bundle / chunk discipline.** `vite.config.ts:43-55` manually chunks `pdfjs-dist` into `pdfjs-vendor`. No code-splitting per view.
- **Type holes are localized.** All `any` / `as any` usage is in test setup and two PDF.js boundary casts.
- **Svelte 4 legacy syntax everywhere.** All components still use `export let`, `on:click`, `$:`. Svelte 5.20 supports this in legacy mode but the new syntax is the recommended path.

## Positive findings

- **No XSS sinks.** Every server-supplied string flows through Svelte's auto-escaped `{}` interpolation.
- **Excellent modal focus management.** `Modal.svelte:55-111` implements a capture-phase keydown trap, Tab/Shift+Tab cycle, focus restoration on close, and an idempotent `closeModal`.
- **WAI-ARIA tab pattern on the primary nav.** `TabRibbon.svelte:60-82` implements the full tablist pattern: roving tabindex, `aria-selected`, Home/End jump to first/last, arrow keys cycle, `tick().then(focus())`.
- **Skip-to-content link.** `App.svelte:57-62` has a `sr-only focus:not-sr-only` skip link.
- **Auth header routing is explicit and tested.** `pickBearerForUrl` maps URL prefixes to per-service tokens.
- **Bearer token never in WebSocket URL.** Sends session token as the first frame after open.
- **NDJSON robustness on the WS wire.** Splits concatenated frames, tolerates trailing newlines, logs and skips malformed lines.
- **View-mount discipline.** `App.test.ts` verifies only the active view is mounted.
- **Reduced-motion preference honored globally.** `app.css:175-184` shortens every `transition` / `animation` to 0.01 ms under `prefers-reduced-motion: reduce`.
- **Theme variables are flipped, not branched.** `app.css:88-106` overrides the same `--color-*` tokens under `html.light`.
- **Object URL lifecycle is correct for PDFs.** `pdfPreview.ts:117-160` revokes the previous `blobUrl` before creating a new one.
- **WS reconnect is bounded with exponential backoff + jitter.** `min(2^retry * 1s, 30s) + random(0..200ms)`, capped at 5 attempts.

## Coverage gaps

- **Runtime behaviour I could not verify from static reads:** actual screen-reader announcement; whether the `Toggle` label/button overlap double-toggles in any specific browser; whether `<a href="/">` triggers a same-tab reload; whether the 401 toast storm actually occurs under the current server config.
- **No visual contrast audit tool was run.** WCAG contrast ratios were computed by hand.
- **No audit of the production `static/` build output.**
- **Backend interop that the frontend depends on but doesn't enforce** is documented elsewhere.

## A11y quick-check

| Concern | Status | Notes |
|---------|--------|-------|
| All images have alt | YES | `<img alt="Page N">` in `PageCanvas.svelte:147`; all SVGs `aria-hidden="true"` |
| All form inputs labeled | YES | `Input.svelte:48-49`; `Select.svelte:27-29` |
| Focus visible | YES | `focus-visible:ring-2 focus-visible:ring-brand` standard recipe |
| Keyboard navigation complete | PARTIAL | TabRibbon has full ARIA tab pattern; Modal has full focus trap. `SettingsView` namespace tabs (F3.13) and the Workstation processing overlay (F3.12) do not |
| Color contrast | PARTIAL | `--color-foreground-subtle` on dark surfaces ~3.9:1 (F3.17) — fails AA |
| ARIA live regions for async | PARTIAL | TabRibbon + PipelineProgress OK; ToastContainer missing (F3.1) |
