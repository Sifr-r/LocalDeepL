# OmniScribe Frontend — QA Report

> Scope: the Svelte 5 + Tailwind v4 SPA in `frontend/`.
> Date: 2026-08-17.
> Method: static review of every component under `src/lib/components/`, the
> design system at `DESIGN_SYSTEM.md`, the CSS at `src/app.css`, plus
> `npm run lint` / `npm run check` / `npm test` / `npm run build`.

## TL;DR

The frontend has a **real, well-maintained design system** — semantic
tokens, primitive components (Button / Card / Input / Select / Toggle /
Badge / Modal / SectionHeader / TabRibbon / Toast), motion rules, and an
explicit `@theme` block in `app.css`. Almost every view is built on top
of those primitives. **Type-checking is clean** (`svelte-check found 0
errors and 0 warnings`) and **all 112 unit tests pass**.

What's missing is the **last 10% of polish**: the linter is currently
failing on 7 unused-import errors (so the CI gate is open), one view
hand-rolls form controls instead of using `Input` / `Select`, the h2
type style diverges from the design system in every view, a dev-only
`Showcase.svelte` is stale and would mislead reviewers, and there is
**no `prefers-reduced-motion` support** for the connection ping, the
ambient-glow blobs, or the toasts.

The good news: every issue I found is a localised, mechanical fix.
None of them require a redesign.

---

## Current state

| Gate                          | Result                                                         |
| ----------------------------- | -------------------------------------------------------------- |
| `npm run check` (svelte-check) | **0 errors, 0 warnings**                                        |
| `npm test` (vitest)            | **112/112 passing** across 16 files in 2.28s                   |
| `npm run lint` (eslint)        | **FAIL — 7 errors** (all `no-unused-vars` — see P0-1)          |
| `npm run build` (vite)         | **OK** in 1.52s                                                |
| Bundle size                    | `index.js` 145.6 kB (gzip 42.8 kB) · `pdfjs-vendor` 433 kB (gzip 128.7 kB) · `index.css` 48.2 kB (gzip 8.9 kB) · `vendor.js` 47.1 kB (gzip 18 kB) |

---

## Strengths — what's working

- **Token layer is real, not a wish-list.** `src/app.css` declares
  every semantic color, font, radius, and the `light` flip in
  `html.light` — the dark/light switch is one CSS class flip, no JS.
  Components consistently reach for `bg-card` / `text-foreground-muted`
  / `border-border` instead of raw `slate-*` (0 hits in `lib/`).
- **Primitive library is mature.** 12 components in `ui/`, all with
  matching focus rings (`ring-2 ring-brand/20`), matching border
  states, and consistent padding scales. The Button primitive handles
  5 variants × 3 sizes and a `loading` prop that swaps the label for
  a spinner — `WorkstationView.svelte:188-201` uses it correctly.
- **Accessibility is largely correct.** Modal has focus trap, ESC,
  click-outside, and prev-focus restoration (`Modal.svelte:55-145`).
  TabRibbon uses WAI-ARIA `tablist`/`tab` roles with roving
  `tabindex` (`TabRibbon.svelte:94-119`). Toast uses `role="alert"`
  for errors, `role="status"` otherwise (`ToastContainer.svelte:54`).
  Stage indicator has `role="progressbar"` with proper aria values
  (`PipelineProgress.svelte:56`).
- **Auth handling is well thought through.** `api/client.ts:49-56`
  picks the right bearer per route group. Auth tokens are stored in
  `sessionStorage` instead of `localStorage` (audit L6 fix),
  and a one-shot migration drops any pre-fix tokens from localStorage
  on load (`appStore.ts:63-72`).
- **PDF.js lifecycle is clean.** `PdfMiniViewer.svelte` uses a
  render-epoch + `pendingCancels` set to abort in-flight paints when
  the source changes — exactly the right pattern for PDF.js.
- **Test coverage is decent for a UI app.** 112 tests cover the
  websocket protocol, the auth-bearing API client, store
  dependencies, the progress pipeline, the design-system primitives,
  and App-level smoke. No flaky behaviour observed.

---

## P0 — Fix this week (blockers)

### P0-1 — Lint gate is broken (7 errors)

`npm run lint` currently exits **1**, so the "fast gate" is
failing for every PR. All seven are `@typescript-eslint/no-unused-vars`:

| File:Line                                       | Symbol                        |
| ----------------------------------------------- | ----------------------------- |
| `src/lib/api/__tests__/websocket.test.ts:1`     | `Mock`                        |
| `src/lib/components/workstation/WorkstationView.svelte:2` | `get` (from `svelte/store`) |
| `src/lib/services/workstationService.ts:55`     | `PreprocessToggle`            |
| `src/lib/stores/appStore.ts:16`                 | `documentStore`               |
| `src/lib/stores/appStore.ts:16`                 | `defaultDocumentModel`        |
| `src/lib/stores/appStore.ts:17`                 | `jobStore`                    |
| `src/lib/stores/appStore.ts:17`                 | `defaultJobState`             |

**Root cause for the `appStore.ts` cluster** — the comment at
`appStore.ts:12-15` says the imports exist to break a circular
dependency, then `appStore.ts:20-21` re-exports the names. The
TypeScript compiler sees the re-exports, but `eslint-plugin-svelte`'s
`no-unused-vars` rule only counts **local reads**, not re-exports. Fix
either by (a) using `export { documentStore, defaultDocumentModel, jobStore, defaultJobState } from './documentStore'` re-export syntax directly
in the import statement, or (b) adding a `// eslint-disable-next-line`
above each line with a one-line `why`. (a) is cleaner.

For the other four: just delete the unused symbol.

### P0-2 — Stale dev-only `Showcase.svelte`

`src/lib/components/dev/Showcase.svelte` is not imported anywhere
(verified with `grep -r "Showcase" src/` — zero matches), but it's
23 KB of code that contradicts the design system:

- Line 30: `Phase 1+2 — the foundation the real screens will use next.`
  (stale project status).
- Line 106: `Geist display + Inter body + JetBrains Mono for
  identifiers only.` — **wrong fonts**. The actual system uses
  Sora + Fraunces.
- Lines 14-15: imports `Input`, `Select`, `Card`, etc. that are also
  imported in real views — same source of truth, no fork.
- The file's own docstring says "**can be removed once Phase 3
  lands**". Phase 3+ is long done.

**Action:** delete the file. It's actively misleading.

### P0-3 — `index.html` uses raw slate instead of the token layer

`frontend/index.html:2`:

```html
<html lang="en" class="dark h-full w-full overflow-hidden bg-slate-950 text-slate-100 antialiased font-sans">
```

`DESIGN_SYSTEM.md` §1.3 explicitly bans this. The `<html>` element
is the only thing visible before CSS loads, so this is the pre-mount
flash of unstyled content. Replace with semantic tokens in `app.css`
under `@layer base`:

```css
html {
  background-color: var(--color-app);
  color: var(--color-foreground);
}
```

…and strip the `bg-slate-950 text-slate-100` from the markup.

---

## P1 — High priority (next sprint)

### P1-1 — Every view diverges from the h2 type spec

`DESIGN_SYSTEM.md` §2.2 says:

> `h2` — `24 / 32` — `text-2xl font-semibold font-display`

Reality: I grepped the codebase and found `text-2xl` once (Showcase)
and `text-xl font-bold` **6 times** across all the real views:

- `SettingsView.svelte:105`
- `JobHistoryView.svelte:75`
- `ExtractionView.svelte:125`
- `TranslationView.svelte:173`
- `TranscriptionView.svelte:132`
- `GlossaryView.svelte:153`

All six use `text-xl font-bold`, not `text-2xl font-semibold
font-display`. This is consistent (the team is doing the same wrong
thing everywhere) but it means **the type scale is, in practice, one
step smaller and one step heavier than documented**.

**Action:** either change the spec to match reality, or fix the
six call sites. I recommend fixing — `text-2xl` is a stronger page
title for a workspace where users can have multiple browser tabs
open.

### P1-2 — `prefers-reduced-motion` is not honored

Grep for `matchMedia` / `prefers-reduced-motion` returned **zero
hits** in the source. The following always run:

- `ambient-glow-1` / `ambient-glow-2` — `floatGlow1` 12s loop +
  `pulseGlow` 8s loop (`app.css:228-236`, `App.svelte:56-57`).
- `animate-ping` on the live connection dot (`TabRibbon.svelte:139`).
- `animate-pulse` on the "checking" / "loading" states
  (`TabRibbon.svelte:146`, `MetadataPanel.svelte` skeleton rows,
  `JobHistoryView.svelte:117`).
- `animate-spin` on the Button `loading` state and several inline
  loaders (`Button.svelte:68`, `TranscriptionView.svelte:249`).
- `animate-slide-in` on every toast (`ToastContainer.svelte:50`).

**Action:** add to `app.css`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

…and replace the two `animate-ping`/`animate-pulse` decorative
elements with a static dot in the reduced-motion branch. Total
expected change: ~10 lines.

### P1-3 — Three different "active tab" patterns

The TabRibbon is the documented pattern (`DESIGN_SYSTEM.md` §4.7).
But three places re-implement it inline:

- `GlossaryView.svelte:163-179` — pill-style buttons on a `surface-inset`.
- `ExtractionView.svelte:132-148` — same pill pattern, but for
  template selection (semantically NOT a tab; it's a radio group).
- `SettingsView.svelte:124-146` — underline pattern
  (`border-b-2 border-brand`), no shared styling.
- `MetadataPanel.svelte:122-149` — segmented control
  (`OCR PDF` / `Text`), styled completely differently from all three.

The team is reaching for "the right thing" but the design system
hasn't given them a primitive. **Action:** add a `<Tabs>` component
(tablist and segmented variants) to `ui/`, then collapse the four
inline patterns into two `<Tabs variant="segmented">` calls and one
`<Tabs variant="underline">` call. ~60 lines of new code, ~80 lines
deleted.

### P1-4 — Hand-rolled form controls in `SettingsView.svelte`

`SettingsView.svelte:178-198` (OCR model ID) and `:264-283`
(translation model ID) hand-roll a raw `<input>` with custom
Tailwind classes inline:

```html
<input id="ocr-model" type="text" ...
  class="flex-1 h-9 px-3 rounded-md text-sm font-mono bg-card text-foreground
         border border-input focus:outline-none focus:ring-2 focus:ring-brand/20
         focus:border-brand transition-colors" />
```

This is exactly the `Input` primitive shape. The `font-mono` is the
only thing that diverges — and `Input` doesn't expose a `font-mono`
prop. **Action:** add a `mono?: boolean` prop to `Input`, or wrap
in a `class="font-mono"` override (which works because the wrapper
class wins), then replace the four hand-rolled inputs. ~15 lines.

### P1-5 — `<label>` for the unlabeled `Select` in `TranslationView.svelte`

`TranslationView.svelte:181-187` and `:189-198` both use
`<Select label="" ariaLabel="...">`. The DESIGN_SYSTEM.md §4.3
explicitly says:

> `Input` and `Select` always have a `label` and a `hint` (or `error`).
> Never label via `placeholder` alone.

There is no visible "Target language" label. A keyboard user gets the
aria-label, but a sighted user has to guess what the dropdown is for.
**Action:** promote the `Select` to a proper labeled control (a small
`form-label` above it, like the rest of the app), or add a visible
inline label. Same fix in `ExtractionView.svelte:332-337` if relevant.

### P1-6 — Modal labels vs Select chevron inconsistency

`Select.svelte:60-67` ships a built-in chevron (per spec). Good. But
`Modal.svelte:194-204` (close button) and `Button.svelte:69` (spinner)
both render inline. That's correct per the spec. **No fix needed
here** — flagging because the audit confirmed.

### P1-7 — `JobHistoryView` "Cancel" link is visually weak

`JobHistoryView.svelte:158-167`:

```svelte
<button type="button" on:click={() => cancelJob(job.id)}
  class="text-xs font-medium text-danger hover:underline">
  Cancel
</button>
```

A `text-danger hover:underline` text link in a row full of strong
destructive contexts (the `Clear all` button is a proper
`Button variant="danger"` with a trash icon). It doesn't read as
destructive to a first-time user.

**Action:** use `<Button variant="danger" size="sm">Cancel</Button>`
or a `Badge variant="danger" size="sm" class="cursor-pointer">` click
target. ~5 lines.

---

## P2 — Medium priority

### P2-1 — `Job ID` column uses brand color for a non-action

`JobHistoryView.svelte:130-132` renders the id in `text-brand`:

```svelte
<td class="py-2.5 px-4 font-mono text-xs font-semibold text-brand
           truncate max-w-[120px]" title={job.id}>
  {job.id}
</td>
```

The Job ID is a *read-only identifier*, not a CTA. Brand color in
this context makes the table look like it has a hidden action and
competes with the actual danger button on the right. The
`DESIGN_SYSTEM.md` rule 0.4 says mono is for identifiers, with
`text-foreground-muted` for secondary, and the Brand color is for
"selected state, primary CTA, focus accent". This violates that.

**Action:** `text-foreground` or `text-foreground-muted` (with the
mono + size keeping it scannable).

### P2-2 — Sub-section titles hand-roll a `SectionHeader`

`SettingsView.svelte:387` (Upload limits & environment), `:152`
(per-card SectionHeader call already correct),
`TranslationView.svelte:245,286` ("Source input" / "Translated
output"), `ExtractionView.svelte:156,193` (similar), and
`TranscriptionView.svelte:159,233` (same) all use:

```svelte
<h3 class="font-display text-xs font-semibold uppercase tracking-wider
           text-foreground-muted -mb-2">
  Section title
</h3>
```

This is **the exact `SectionHeader` recipe minus the `divider`**
(`SectionHeader.svelte:19-34`). Since the design system already
has the component, just use it:

```svelte
<SectionHeader title="Section title" divider={false} />
```

~12 instances collapsed into one. The `h3` also becomes `h4`,
which is actually correct (sub-section of an h2 view).

### P2-3 — File input styling bypasses the design system

`TranscriptionView.svelte:161-168` and `GlossaryView.svelte:341-349`
hand-roll a styled `<input type="file">` with `file:bg-brand
file:text-brand-foreground` etc. It's not in the `Input` primitive
because the file input has a separate visual contract (the OS file
picker button), but the design system doesn't have a `<FileInput>`
either. **Action:** add a `FileInput` primitive, or accept the
bypass and document it in `DESIGN_SYSTEM.md` §4.

### P2-4 — Icon stroke-width inconsistency

The design system says `stroke-width="1.8"` for UI chrome, `"2"` for
glyphs that need weight, `"3"` for checkmarks. I found the system
mostly follows this, but several places use `2` where `1.8` is
specified (`WorkstationView.svelte:194` play icon, `MetadataPanel
svelte:178` download icon, `JobHistoryView.svelte:86` refresh icon,
several more). Subtle, but it makes the icon set feel slightly
louder than intended. **Action:** quick pass to drop `2` → `1.8`
except for the cases the spec already calls out.

### P2-5 — No keyboard arrow navigation on `TabRibbon`

`TabRibbon.svelte:94-119` uses `tablist`/`tab` with roving
`tabindex`, which is correct for screen readers, but does not
implement the standard ArrowLeft / ArrowRight / Home / End keyboard
pattern. Keyboard users must Tab through every tab. Not a blocker
(works) but the ARIA spec says arrows are required for `tablist`.

**Action:** ~10 lines, in `TabRibbon.svelte` `on:keydown`.

### P2-6 — `processView` overlay is a `<div hidden>`, not a real modal

`WorkstationView.svelte:221-227` keeps a fixed-position
`<div id="process-view">` in the DOM at all times and toggles
`hidden` (well, actually a class string with `hidden` mixed in,
which is fragile). The `transition-all duration-300` on the
element doesn't actually transition `display`. There's no focus
trap, no `role="dialog"`, and the `id="process-view"` is preserved
for the Playwright test only.

**Action:** if it's only there for the Playwright hook, render a
real `<Modal>` for the progress overlay, then keep a `<div
id="process-view" class="hidden">` (truly hidden) just to satisfy
the selector. The current state is a maintenance hazard (the
overlay's children include `PipelineProgress` which dispatches
events, but the parent treats visibility inconsistently).

### P2-7 — Empty state for "image upload" (non-PDF) is silent

`PageCanvas.svelte:177-190` shows the same "No document loaded"
empty state for both "no upload yet" and "upload failed to render".
The render failure is technically surfaced inside
`<canvas>` via `renderError` (`PageCanvas.svelte:171-175`) but it's
in a 11px footer band, easy to miss. **Action:** promote
`renderError` to a full-card empty state with an icon.

---

## P3 — Polish / nice-to-have

- **`text-[10px]` and `text-[11px]` are used a lot** (Micro text
  in badges, captions in tables, the `Micro` row of the type scale
  is `10/14`). Several places use `text-[11px]` which doesn't fit
  the scale. Expand the scale or commit to 10px everywhere.
- **`font-mono` count is 66.** Most are correct (artifact IDs,
  file sizes, percentages), but some are for stage names, labels,
  and prose. Worth a sweep.
- **Connection status dot color:** the success/ping pulse works,
  but a single color per state (success/online = green,
  checking = amber, offline = red) means an "offline" blink is
  jarring on dark backgrounds. Consider keeping the dot still and
  using the chip text + tooltip to communicate state.
- **`#process-view` is the only place where the design system
  yields to legacy Playwright selectors.** A `// LEGACY`
  comment would help future maintainers.
- **Build is fine but `pdfjs-vendor` is 433 kB (128 kB gz).** It's
  split correctly already, but a PDF.js worker as a separate
  chunk (1.26 MB) is shipped to every page even if the user only
  opens the glossary view. Could lazy-load on first nav to
  Workstation.
- **No "Copy to clipboard" affordance anywhere** despite the
  workstation being the natural place to copy extracted text,
  JSON, or artifact IDs.
- **No skip-to-content link.** With a sticky header and 7 tabs,
  Tab users walk the entire `TabRibbon` to reach the work area.
  A `<a href="#main" class="sr-only focus:not-sr-only">Skip to
  content</a>` would help.

---

## Recommended order of work

1. **Day 1, ~30 min:** P0-1 (lint gate) + P0-2 (delete Showcase)
   + P0-3 (raw slate in index.html). All three are
   mechanical and unblock CI. → `npm run lint` goes green.
2. **Day 1, ~1 hour:** P1-1 (h2 type spec) + P1-2
   (prefers-reduced-motion) + P1-4 (Input primitive in
   SettingsView). Together they tighten the visible quality of every
   view at once.
3. **Day 2, ~2 hours:** P1-3 (Tabs primitive) + P1-7 (Cancel
   button) + P2-2 (SectionHeader pass). Big visual cleanup,
   small code.
4. **Day 3, ~1 hour:** P2-5 (TabRibbon keyboard arrows) +
   P2-6 (process-view real modal) + P2-7 (render-error empty
   state). A11y / robustness.
5. **Sweep later:** P3 items, two weeks out.

No code changes shipped yet — this is a report. Tell me which P0s
to land first and I'll cut the patches.
