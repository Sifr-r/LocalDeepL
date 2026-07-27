---
kind: frontend_style
name: DocuVerse CSS Design System with Dark/Light Theme
category: frontend_style
scope:
    - '**'
source_files:
    - src/local_deepl/static/style.css
    - src/local_deepl/static/css/variables.css
    - src/local_deepl/static/css/layout.css
    - src/local_deepl/static/css/components.css
    - src/local_deepl/static/css/workspace.css
    - src/local_deepl/static/index.html
    - src/local_deepl/static/js/state_and_api.js
    - src/local_deepl/static/js/app.js
---

The frontend styling is implemented as a vanilla CSS design system called "DocuVerse — Warm Ink" with no CSS framework, preprocessor, or build step. All styles are plain CSS files served directly from `src/local_deepl/static/` and loaded via the single entry point `style.css`, which imports five modular sheets in order: `variables.css`, `layout.css`, `components.css`, `workspace.css`, and `modals.css`.

**Design tokens and theming**
- All colors, typography, spacing, shadows, and motion primitives are declared as CSS custom properties in `:root` (dark theme) and overridden under `[data-theme="light"]`. The palette centers on a warm amber primary (`--primary: #E8A838`) against deep charcoal backgrounds (`--bg-main: #12141A`), with semantic tokens for success/error/info states, borders, surfaces, and text hierarchy.
- Typography uses Google Fonts Fraunces (display serif) and Sora (body sans-serif), plus JetBrains Mono/Fira Code for monospace code. Font families are exposed through `--font-display`, `--font-body`, `--font-mono` variables.
- Motion uses shared cubic-bezier easing curves (`--ease-out`, `--ease-spring`) and duration tokens (`--duration-fast: 0.15s`, `--duration-med: 0.25s`, `--duration-slow: 0.4s`).
- Theme toggling is driven by setting `data-theme="dark|light"` on `<html>` and persisted to `localStorage`; the default follows `prefers-color-scheme`.

**CSS methodology**
- BEM-like class naming without a formal methodology: descriptive component names like `.drop-zone-premium`, `.settings-card`, `.ai-tab-btn`, `.glass-progress-overlay`, `.modal-backdrop`.
- No CSS-in-JS, no SCSS/Sass, no Tailwind, no PostCSS — pure CSS with `@import` composition at the top-level `style.css`.
- Responsive breakpoints are defined inline in `layout.css` using `@media (max-width: 1200px)` and `@media (max-width: 768px)` to collapse the three-column workstation grid into stacked layouts and hide side panels on mobile.

**Component library (hand-built)**
- Reusable UI primitives include: drop zones (`.drop-zone-premium`), file info cards (`.file-info-premium`), settings cards (`.settings-card`), segmented radio controls (`.segmented-mini`), buttons (`.btn-run`, `.btn-run-sm`, `.btn-chip`, `.btn-icon-sm`, `.btn-mini`), status dots (`.status-dot`), tabs (`.tab-ribbon` / `.ai-tab-btn`), progress overlays (`.glass-progress-overlay` with `.progress-card`), toast notifications (`.toast-container`), modals (`.modal-backdrop` / `.modal-card`), JSON visual cards (`.json-card-grid`), and rich text output boxes (`.text-box-premium`, `.text-box-rich-content`).
- The PDF viewer layer adds SVG bbox overlays (`.pdf-bbox-svg`), selectable text layers (`.pdf-text-layer`), annotation layers, search highlights, continuous/spread layout modes, bookmarks, and a compare view — all styled purely in `workspace.css`.

**JavaScript integration**
- State and DOM references are centralized in `js/state_and_api.js` via a `state` object and a `refs` map of cached element selectors.
- Application orchestration lives in `js/app.js`: WebSocket-based progress streaming, drag-and-drop upload, OCR pipeline triggering, Markdown rendering via CDN-loaded `markdown-it`, translation and structured data extraction flows, and app-shell tab switching.
- Additional modules handle thumbnails (`thumbnails.js`) and workspace UI logic (`workspace_ui.js`).

**HTML structure**
- A single `index.html` defines the full SPA shell: a top ribbon nav (Workstation / Translation views), a three-column workstation (left controls, central PDF viewport, right AI output tabs), and a dedicated translation view. Assets are versioned via query strings (e.g., `?v=5`, `?v=10`).