---
kind: frontend_style
name: CSS Variables + Vanilla JS Single-Page Workstation UI
category: frontend_style
scope:
    - '**'
source_files:
    - src/local_deepl/server.py
    - src/local_deepl/static/index.html
    - src/local_deepl/static/style.css
    - src/local_deepl/static/css/variables.css
    - src/local_deepl/static/css/components.css
    - src/local_deepl/static/js/app.js
---

The frontend is a vanilla HTML/CSS/JS single-page application served by FastAPI from `src/local_deepl/static/`. There is no build step, framework, or component library — styling and behavior are written directly in plain CSS and JavaScript files.

**Styling system**
- Design tokens live in `css/variables.css` as CSS custom properties (`--primary`, `--bg-main`, `--surface`, `--text-main`, `--radius-*`, `--shadow-*`, etc.) under a `:root` block plus a `[data-theme="dark"]` override, enabling light/dark mode toggling via the `data-theme` attribute on `<html>`.
- The root stylesheet `style.css` uses `@import` to compose modular sheets: `variables.css`, `layout.css`, `components.css`, `workspace.css`, `modals.css`. This is the only CSS entry point; nothing else imports these files.
- A large inline `<style>` block in `index.html` overrides theme variables for the "DocuVerse" workstation view (purple/cyan palette) and defines the three-column grid layout, glassmorphic panels, ambient glow effects, progress overlay, tab ribbon, thumbnail strip, confidence heatmap toggle, and JSON card grid. This inline style is the primary visual identity of the current UI.
- No CSS-in-JS, SCSS, Tailwind, or utility-first approach is used. All styles are authored as conventional class selectors.

**JavaScript architecture**
- `js/app.js` is the main orchestrator: it initializes theme persistence (`localStorage`), connects a WebSocket for real-time OCR/translation progress, wires drag-and-drop upload, manages top-level app tabs (Workstation / Translation), and drives the right-side AI workstations (Markdown, Translator, Schema Extractor).
- Supporting modules: `state_and_api.js` (shared state and API helpers), `thumbnails.js` (page thumbnail strip), `workspace_ui.js` (PDF canvas rendering, bbox overlay, zoom/navigation).
- Markdown rendering uses the CDN-loaded `markdown-it` library; content is sanitized via `DOMParser` before insertion into the DOM.

**Server wiring**
- `server.py` mounts `/static` via `fastapi.staticfiles.StaticFiles(directory=...)` and serves `index.html` at the root route. The static directory is `Path(__file__).parent / "static"`.

**Conventions developers should follow**
- Add new design tokens exclusively in `css/variables.css` under `:root` and its `[data-theme="dark"]` counterpart; never hard-code colors in components.
- Place reusable component styles in `css/components.css` (buttons, inputs, tabs, accordions, toasts, badges); layout-specific rules go in `css/layout.css` / `css/workspace.css`; modal-only rules in `css/modals.css`.
- Keep the composition file `style.css` as the single import hub — do not import CSS from other locations.
- Theme switching must set `data-theme="light|dark"` on `<html>` and persist via `localStorage('theme')`; avoid per-element color overrides.
- New UI logic belongs in `js/app.js` (orchestration) or a dedicated module under `js/` imported from `index.html`; avoid scattering event handlers inline in HTML.
- Any third-party client libraries (e.g., `markdown-it`) should be loaded via CDN links in `index.html` rather than bundled.
- The UI is intentionally non-responsive beyond basic viewport sizing; adding breakpoints is acceptable but keep them scoped to the existing three-column workstation layout.