# OmniScribe Design System

> Single source of truth for color, type, spacing, components, and icons.
> Every rule below is enforceable from the existing Svelte 5 + Tailwind v4
> stack. The system has two states right now: the **legacy HSL tokens** in
> `src/app.css` (still used by the ambient-glow layer) and the **semantic
> token layer** that the UI primitives in `src/lib/components/ui/*` are
> written against. The semantic layer is the target — page 1 of this doc
> pins the exact values that the `@theme` block must declare so the
> `bg-card` / `text-foreground` / `text-brand` utility classes that
> every component already uses actually resolve.

## 0. Principles

1. **Semantic over raw.** Always reach for `bg-card` not `bg-slate-900`.
   Raw Tailwind colors are reserved for the `app.css` token layer and
   one-off illustrations.
2. **Dark is the default, light is a class.** `html` ships with
   `.dark`; `html.light` flips the same tokens. Components never branch
   on theme — they consume the same class names in both.
3. **Indigo is a feature, not a chrome.** Brand color carries meaning
   (selected tab, primary CTA, focus ring). Decoration should stay
   neutral.
4. **Mono is for identifiers, not text.** `font-mono` is for artifact
   IDs, file sizes, version pills, and progress percentages — never for
   paragraphs.
5. **One component, all primary actions.** No bespoke button styles per
   page. If a button doesn't fit a `Button` variant, the variant is
   wrong, not the component.

---

## 1. Color System

### 1.1 Semantic token table (the target)

These are the class names every component in `src/lib/components/ui/`
already uses. The `@theme` block at the bottom of this section is the
canonical declaration that makes them resolve.

| Token            | Class                  | Dark (default) | Light         | Use for                                |
| ---------------- | ---------------------- | -------------- | ------------- | -------------------------------------- |
| `bg-app`         | `bg-app`               | `#020617`      | `#f8fafc`     | Page background (root `<div>`)         |
| `bg-card`        | `bg-card`              | `#0f172a`      | `#ffffff`     | Surface 1 — most cards, inputs         |
| `bg-card-raised` | `bg-card-raised`       | `#1e293b`      | `#f1f5f9`     | Surface 2 — nested groups, inset wells |
| `bg-muted`       | `bg-muted`             | `#334155`      | `#e2e8f0`     | Hover/active fill, toggle track, chips |
| `bg-overlay`     | `bg-overlay`           | `rgb(2 6 23 / .8)` | same      | Modal backdrops                        |
| `bg-brand`       | `bg-brand`             | `#6366f1`      | `#4f46e5`     | Primary CTA, active tab, focus accent  |
| `text-foreground`| `text-foreground`      | `#f1f5f9`      | `#0f172a`     | Default body text                      |
| `text-foreground-muted` | `text-foreground-muted` | `#94a3b8` | `#475569`  | Secondary text, labels, captions       |
| `text-foreground-subtle` | `text-foreground-subtle` | `#64748b` | `#64748b` | Tertiary, hint copy                    |
| `text-brand`     | `text-brand`           | `#818cf8`      | `#4f46e5`     | Brand-accented text                    |
| `text-success`   | `text-success`         | `#22c55e`      | `#15803d`     | Completed state, positive deltas       |
| `text-warning`   | `text-warning`         | `#f59e0b`      | `#b45309`     | In-progress, attention needed          |
| `text-danger`    | `text-danger`          | `#f43f5e`      | `#be123c`     | Errors, destructive text               |
| `border-border`  | `border-border`        | `#1e293b`      | `#e2e8f0`     | Default 1px divider                    |
| `border-input`   | `border-input`         | `#334155`      | `#cbd5e1`     | Form-control borders                   |
| `border-brand`   | `border-brand`         | `#6366f1`      | `#4f46e5`     | Focus/active outline                   |

Tailwind v4 also auto-generates opacity variants from these (`bg-brand/10`,
`border-success/30`, `text-foreground/5`). Use the `/N` syntax for tints —
do not hand-write `bg-[#...]`.

### 1.2 Legacy HSL tokens (kept for the ambient-glow layer only)

`app.css` still defines the indigo/cyan/magenta HSL glow vars used by
`floatGlow1/2/3` and `pulseGlow`. Do **not** consume these from
components — they exist to back the two `radial-gradient` blobs in
`App.svelte` and nothing else. The mapping:

| HSL var           | Value           | HSL function used by |
| ----------------- | --------------- | -------------------- |
| `--glow-1`        | `260 100% 65%`  | `.ambient-glow-1`    |
| `--glow-2`        | `195 100% 50%`  | `.ambient-glow-2`    |
| `--brand-primary` | `250 84% 67%`   | (deprecated — replaced by `bg-brand`) |

### 1.3 Do / Don't — color

**DO**

```svelte
<button class="bg-brand text-brand-foreground hover:bg-brand/90">Run OCR</button>
<p class="text-foreground-muted">Last run 3 minutes ago</p>
<div class="bg-card border border-border">…</div>
```

**DON'T**

```svelte
<!-- ❌ hard-coded slate — bypasses the theme switch -->
<button class="bg-indigo-600 text-white">Run OCR</button>

<!-- ❌ raw hex value -->
<div class="bg-[#0f172a]">…</div>

<!-- ❌ legacy HSL token used in a component -->
<button class="bg-brand-primary">…</button>
```

---

## 2. Typography

### 2.1 Font families

Three families, three jobs. Both files are loaded from Google Fonts in
`index.html`.

| Family    | CSS var             | Stack                       | Used by                              |
| --------- | ------------------- | --------------------------- | ------------------------------------ |
| Display   | `font-display`      | `'Fraunces', Georgia, serif`| `h1`–`h3`, modal titles, pipeline %  |
| Body      | `font-sans` (body)  | `'Sora', system-ui, sans`   | All body copy, buttons, labels       |
| Mono      | `font-mono`         | system mono (`sfmono`-ish)  | Artifact IDs, file sizes, percentages|

**`font-display`** is bound to `Fraunces` via the `@theme` `--font-serif-display`
token. **Body** is `Sora` via `--font-sans`. Apply `font-mono` per
element, not globally — see rule 0.4.

### 2.2 Type scale

| Role     | Size       | Weight   | Family   | Tailwind           |
| -------- | ---------- | -------- | -------- | ------------------ |
| `h1`     | `30 / 36`  | 600      | display  | `text-3xl font-semibold font-display` |
| `h2`     | `24 / 32`  | 600      | display  | `text-2xl font-semibold font-display` |
| `h3`     | `18 / 28`  | 600      | display  | `text-lg font-semibold font-display`  |
| Body     | `14 / 20`  | 400      | body     | `text-sm`                             |
| Strong   | `14 / 20`  | 500      | body     | `text-sm font-medium`                 |
| Caption  | `12 / 16`  | 400      | body     | `text-xs text-foreground-muted`       |
| Micro    | `10 / 14`  | 500 UPPER| body     | `text-[10px] font-medium uppercase tracking-wider` (section labels, stage names) |

The 14/20 body / 12/16 caption pair is the workhorse — every panel uses
exactly these two. Anything bigger is reserved for a real page-level
title (used ≤ 1× per view).

### 2.3 Do / Don't — type

**DO**

```svelte
<h2 class="text-2xl font-semibold font-display">Translation memory</h2>
<p class="text-sm text-foreground">The page has 12 paragraphs.</p>
<span class="font-mono text-xs text-foreground-muted">tx-7b91f3a2</span>
```

**DON'T**

```svelte
<!-- ❌ Tailwind default heading weight 700 — too heavy next to Fraunces -->
<h2 class="text-2xl font-bold">Translation memory</h2>

<!-- ❌ Using Inter/Roboto — they aren't loaded -->
<p class="font-inter text-sm">…</p>

<!-- ❌ Mono for prose -->
<p class="font-mono text-sm">Document uploaded successfully.</p>
```

---

## 3. Spacing & Grid

### 3.1 Spacing scale (4px base)

Tailwind's default scale is already 4px-aligned. Use it directly — do
not invent custom values.

| Token     | px     | When                                          |
| --------- | ------ | --------------------------------------------- |
| `1`       | `4`    | Tight stack inside a single label             |
| `1.5`     | `6`    | Inline icon ↔ text gap                        |
| `2`       | `8`    | Default gap between form fields               |
| `3`       | `12`   | Between sections inside a card                |
| `4`       | `16`   | Card padding (`Card padding="md"` default)    |
| `5`       | `20`   | Between sibling cards                         |
| `6`       | `24`   | Page padding on workstation / settings views  |
| `8`       | `32`   | Major section breaks (only inside a view)     |

**Rule of thumb:** inside a card → multiples of 1/1.5/2. Between cards →
3/4/5. Page-level whitespace → 6/8.

### 3.2 Layout grid

Two named grids cover the whole app.

**Workstation (3-column OCR layout)**
```html
<div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
  <div class="lg:col-span-3">…settings…</div>
  <div class="lg:col-span-6">…canvas…</div>
  <div class="lg:col-span-3">…metadata…</div>
</div>
```
- Stacks 1-column on `< lg`, expands to 3/6/3 on `lg+`.
- All three columns use `min-w-0` so children can `truncate`.
- The middle column always has `min-h-[600px]` to prevent the canvas
  collapse before pdf.js renders.

**Two-pane editor (Translation, Settings, Glossary)**
```html
<div class="grid grid-cols-1 lg:grid-cols-2 gap-5">…</div>
```

### 3.3 Page rhythm

| Surface              | Padding      | Notes                                      |
| -------------------- | ------------ | ------------------------------------------ |
| Root view (`<main>`) | `p-6`        | Every top-level view starts with `p-6`     |
| Card body            | `p-4`        | `Card padding="md"` default                |
| Card section divider | `pt-3 mt-3 border-t` | `Card` adds automatically when `slot="footer"` is used |
| Modal                | `p-6`        | `Modal` is fixed; body scrolls inside      |
| Page top (header)    | `h-14`       | The `TabRibbon` is `h-14` and sticky       |

### 3.4 Do / Don't — spacing

**DO**

```svelte
<div class="space-y-4">                  <!-- 16 between fields -->
  <Input label="API base URL" />
  <Input label="API key" />
  <Input label="Model" />
</div>
```

**DON'T**

```svelte
<!-- ❌ Arbitrary spacing value -->
<div class="space-y-[13px]">…</div>

<!-- ❌ Magic number padding not on the scale -->
<div class="p-[18px]">…</div>
```

---

## 4. Components

Every component in `src/lib/components/ui/` is a primitive — pass
props, get the right variant. Do not hand-roll new buttons, inputs,
or modals in views.

### 4.1 Button

**Variants**

| Variant     | When                                            | Class shape (Tailwind v4)         |
| ----------- | ----------------------------------------------- | --------------------------------- |
| `primary`   | One per view, the hero action                   | `bg-brand text-brand-foreground`  |
| `secondary` | Paired actions next to a primary                | `bg-card-raised text-foreground border border-border` |
| `ghost`     | Tertiary, icon-only, toolbar buttons            | `bg-transparent text-foreground-muted hover:bg-muted` |
| `danger`    | Destructive (delete, cancel job)                | `bg-danger/15 text-danger border border-danger/30` |
| `outline`   | Secondary CTA that shouldn't compete with primary | `bg-transparent text-brand border border-brand/40` |

**Sizes**

| Size  | Height | Horizontal pad | Text size |
| ----- | ------ | -------------- | --------- |
| `sm`  | `32`   | `12`           | `12`      |
| `md`  | `36`   | `16`           | `14` (default) |
| `lg`  | `44`   | `20`           | `14`      |

**Rules**

- One `primary` button per view. Two primaries = a layout bug.
- `loading` swaps the label for a spinner. Don't also add a spinner
  manually inside the slot.
- `fullWidth` only on the lone hero CTA (e.g. "Start processing").
- Icons live in the slot, sized `w-4 h-4`, `stroke="currentColor"`.

**DO**

```svelte
<Button variant="primary" size="lg" fullWidth on:click={startProcessing}>
  <svg class="w-4 h-4" …>…</svg>
  <span>Start processing</span>
</Button>
```

**DON'T**

```svelte
<!-- ❌ Two primary buttons next to each other -->
<Button variant="primary">Save</Button>
<Button variant="primary">Save and run</Button>

<!-- ❌ Manual spinner + label when loading prop exists -->
<Button>
  {#if isProcessing}<span class="animate-spin">○</span>Running…{/if}
</Button>
```

### 4.2 Card

The universal panel. Owns background + border + radius; padding is a
separate decision.

| Variant   | Use                                                  |
| --------- | ---------------------------------------------------- |
| `default` | Top-level cards (uses `bg-card` + `border-border`)   |
| `raised`  | Nested groups inside another card (`bg-card-raised`) |
| `inset`   | Soft groups, no border (`bg-card-raised border-0`)   |

**Padding** defaults to `md` (`p-4`). Use `lg` (`p-6`) for hero panels
like the pipeline progress overlay; `sm` (`p-3`) for dense lists; `none`
when the slot provides its own padding.

**Rule:** never set `bg-card` or `border` on a child of a Card — the
Card already provides the surface.

**DO**

```svelte
<Card padding="md">
  <SectionHeader title="Pipeline settings" />
  <Select … />
</Card>
<Card variant="raised" padding="sm" class="mt-3">…</Card>
```

**DON'T**

```svelte
<!-- ❌ Card inside Card; just use the inset variant -->
<Card><Card>…</Card></Card>

<!-- ❌ Manually setting surface tokens on a wrapper -->
<Card><div class="bg-card border border-border rounded-md">…</div></Card>
```

### 4.3 Input / Select / Toggle

Identical focus ring + border state across all three.

| State   | Border              | Ring                |
| ------- | ------------------- | ------------------- |
| Idle    | `border-input`      | none                |
| Focus   | `border-brand`      | `ring-2 ring-brand/20` |
| Error   | `border-danger`     | `ring-2 ring-danger/20` |
| Disabled| `border-input opacity-50` | n/a            |

**Rules**

- `Input` and `Select` always have a `label` and a `hint` (or `error`).
  Never label via `placeholder` alone.
- `Select` chevron is a built-in `svg` — do not add another one.
- `Toggle` label goes in the `label` prop, not the slot. The slot is
  for an optional badge or meta.
- `Toggle` rows sit inside `surface-inset` (an `inset` Card variant
  with `p-3`) when there are 3+ of them.

**DO**

```svelte
<Input id="api-base" label="OCR API base" placeholder="http://localhost:1234/v1"
       bind:value={apiBase} hint="OpenAI-compatible endpoint." />

<div class="surface-inset p-3 space-y-1">
  <Toggle id="t-deskew" label="Deskew image" bind:checked={deskew} />
  <Toggle id="t-denoise" label="Denoise" bind:checked={denoise}
          description="Reduces scanning noise before OCR." />
</div>
```

**DON'T**

```svelte
<!-- ❌ Label-by-placeholder -->
<input placeholder="OCR API base" />

<!-- ❌ Toggle without label prop -->
<Toggle><span>Deskew image</span></Toggle>

<!-- ❌ Hand-rolled select -->
<select class="bg-slate-800 text-white px-2 py-1">…</select>
```

### 4.4 Badge

Six semantic variants. Always small (`h-5 px-2 text-[10px]`) unless
used as a status pill where `md` (`h-6 px-2.5 text-xs`) is allowed.

| Variant   | Use                                       |
| --------- | ----------------------------------------- |
| `neutral` | Generic tags, version pills               |
| `brand`   | Selected state, "active" markers          |
| `success` | Completed, high confidence                |
| `warning` | In-progress, attention needed             |
| `danger`  | Failed, error state                       |
| `info`    | Neutral-but-notable (replaces `brand` when used for non-actionable info) |

**Rule:** all six variants use a 30%-tinted background and 100% text.
Do not adjust the tint ad hoc — `bg-brand/15 border-brand/30 text-brand`
is the fixed recipe.

### 4.5 Modal

`Modal` handles backdrop, focus management, ESC-to-close, and the
title row. The `footer` slot replaces the default `pt-4 border-t` —
use it for a right-aligned flex row of `Button`s.

**Rule:** keep `maxWidth` ≤ `lg` (32rem) for form modals, `xl` (36rem)
only for the Export / Provider dialogs which need scroll room.

### 4.6 SectionHeader

`SectionHeader` is a `h4` rendered as `text-xs font-semibold tracking-wider
uppercase text-foreground-muted` over a 1px divider. Use it inside
any Card to label a logical group.

**Rule:** do not skip levels. Inside a `Card padding="lg"`, the
hierarchy is `SectionHeader` (h4) → body content. Page-level `h2` lives
on the view, not inside cards.

### 4.7 TabRibbon

`TabRibbon` is the only place the active-tab pattern lives. The
active tab uses `bg-brand text-brand-foreground`; inactive tabs are
`text-foreground-muted hover:text-foreground hover:bg-muted`. Tab IDs
(`app-tab-btn-*`) are preserved for the Playwright smoke test in
`test_ui.py` — do not rename them.

### 4.8 Toast

`ToastContainer` renders toasts bottom-right with a level-keyed left
accent border (`border-l-brand/success/warning/danger`) and an icon.
Always go through `toastStore.pushToast(level, message)` — never
spawn a toast by hand.

**Rule:** keep messages ≤ 80 chars. One sentence, no terminal periods.

---

## 5. Icon style

### 5.1 Source

Hand-rolled Heroicons-style outlines, inline SVG. Lucide and Heroicons
draw the same way; either is acceptable. We do not pull in an icon
package — every icon in the codebase is already inline and consistent.

### 5.2 Anatomy

Every icon follows this exact shape:

```html
<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"
     stroke-width="1.8" aria-hidden="true">
  <path stroke-linecap="round" stroke-linejoin="round" d="…" />
</svg>
```

| Property        | Value                              |
| --------------- | ---------------------------------- |
| `viewBox`       | `0 0 24 24` (always)               |
| `fill`          | `none` (always)                    |
| `stroke`        | `currentColor` (always)            |
| `stroke-width`  | `1.8` for UI chrome, `2` for glyphs that need weight, `3` for checkmarks |
| `stroke-linecap`| `round`                            |
| `stroke-linejoin`| `round`                           |
| `aria-hidden`   | `true` when the icon is decorative (button already has `aria-label`) |
| Decorative spacing | `space-x-1.5` from adjacent text |

### 5.3 Size scale

| Use                          | Tailwind | Pixel |
| ---------------------------- | -------- | ----- |
| Inside `h-5` badge           | `w-3 h-3` | 12   |
| Icon-only `size="sm"` button | `w-3.5 h-3.5` | 14 |
| Default — buttons, toggles, toast | `w-4 h-4` | 16 |
| Empty-state illustrations    | `w-5 h-5` | 20   |

Anything ≥ `w-6 h-6` is a feature illustration, not a UI icon — it goes
in `<svg class="w-6 h-6 text-foreground-muted">` and is never used
inside a `Button` slot.

### 5.4 Color

Icons inherit color from their parent via `stroke="currentColor"`.
Never set `stroke` to a raw hex.

**DO**

```svelte
<Button variant="ghost" size="sm" ariaLabel="Close">
  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M6 18L18 6M6 6l12 12" />
  </svg>
</Button>
```

**DON'T**

```svelte
<!-- ❌ stroke-width 2 + 3 mixed on the same icon -->
<svg … stroke-width="2"><path stroke-width="3" …/></svg>

<!-- ❌ fill="currentColor" on an outline icon (it'll be a solid blob) -->
<svg class="w-4 h-4" fill="currentColor" viewBox="…">…</svg>

<!-- ❌ emoji as an icon -->
<Button>🚀 Start</Button>
```

---

## 6. Motion

Three named animations live in `app.css`; do not introduce new ones
without a design review.

| Name              | Duration | Easing        | Use for                         |
| ----------------- | -------- | ------------- | ------------------------------- |
| `animate-ping`    | 1s       | ease-in-out   | Live status dot (TabRibbon, PipelineProgress) |
| `animate-pulse`   | 2s       | ease-in-out   | Skeleton rows, pending dots     |
| `animate-spin`    | 1s       | linear        | Button `loading` spinner only   |
| `animate-slide-in`| 0.3s     | cubic-bezier(0.16, 1, 0.3, 1) | Toast enter  |

Hover/active transitions: `transition-colors duration-150` on every
interactive element. Never animate layout (width/height) — animate
opacity, transform, and color only.

---

## 7. Token wiring — the canonical `@theme` block

This block, dropped into `src/app.css`, makes every class name
documented above resolve under Tailwind v4. Replace the current
`@theme { ... }` block (which only declares fonts) with this:

```css
@theme {
  /* Fonts */
  --font-sans: 'Sora', system-ui, -apple-system, sans-serif;
  --font-serif: 'Fraunces', Georgia, serif;
  --font-serif-display: 'Fraunces', Georgia, serif;
  --font-mono: ui-monospace, SFMono-Regular, "JetBrains Mono", monospace;

  /* Brand */
  --color-brand: #6366f1;
  --color-brand-foreground: #ffffff;

  /* Surfaces */
  --color-app: #020617;
  --color-card: #0f172a;
  --color-card-raised: #1e293b;
  --color-muted: #334155;
  --color-overlay: rgb(2 6 23 / 0.8);

  /* Foreground (text) */
  --color-foreground: #f1f5f9;
  --color-foreground-muted: #94a3b8;
  --color-foreground-subtle: #64748b;

  /* Borders */
  --color-border: #1e293b;
  --color-border-strong: #334155;
  --color-input: #334155;
  --color-ring: #6366f1;

  /* Semantic */
  --color-success: #22c55e;
  --color-warning: #f59e0b;
  --color-danger: #f43f5e;
  --color-info: #38bdf8;

  /* Radius */
  --radius-card: 0.5rem;
}

html.light {
  --color-app: #f8fafc;
  --color-card: #ffffff;
  --color-card-raised: #f1f5f9;
  --color-muted: #e2e8f0;
  --color-foreground: #0f172a;
  --color-foreground-muted: #475569;
  --color-border: #e2e8f0;
  --color-input: #cbd5e1;
  --color-brand: #4f46e5;
  --color-success: #15803d;
  --color-warning: #b45309;
  --color-danger: #be123c;
}
```

Plus the helper utility layer so primitives can keep their terse
classnames:

```css
@layer components {
  .form-label    { @apply block text-xs font-medium text-foreground-muted mb-1.5; }
  .section-header{ @apply text-xs font-semibold uppercase tracking-wider text-foreground-muted; }
  .surface-inset { @apply rounded-md bg-card-raised border border-border/0; }
}
```

---

## 8. Quick checklist for a new view

Before opening a PR, confirm:

- [ ] Background uses `bg-app`, never `bg-slate-950` directly
- [ ] Every interactive control is a primitive (Button / Input / Select / Toggle)
- [ ] One `primary` button per view
- [ ] Page title is `h2` (`text-2xl font-semibold font-display`); section labels use `SectionHeader`
- [ ] Layout follows the 3-col or 2-col grid from §3.2
- [ ] Icons match the §5.2 anatomy; sizes match §5.3
- [ ] No hard-coded colors, no emoji icons, no raw hex
- [ ] Light mode is checked by toggling `html.classList` (one CSS class flip)
- [ ] Playwright selectors (`app-tab-btn-*`, `view-*`, `start-btn`, `process-view`) are preserved
