# Domain 3 Audit: Frontend Architecture, Accessibility (a11y) & UX

**Auditor:** Lead Frontend & Accessibility Auditor  
**Date:** 2026-08-18  
**Scope:** OmniScribe Web UI & Frontend Architecture (`frontend/src/`)  

---

## Executive Summary

An exhaustive audit of Domain 3 (Frontend Architecture, Accessibility, Svelte 5 / State Management, Security, and UX/API Alignment) was conducted across `frontend/src/`.

The codebase features zero unescaped HTML injection (`{@html}`), consistent Tailwind CSS v4 design token enforcement, robust token-bound WebSocket resilience, and session-isolated auth storage.

However, **17 specific issues** were identified across four audit pillars:

### Severity Summary Table

| Severity | Count | Issue IDs | Summary Description |
| :--- | :---: | :--- | :--- |
| **CRITICAL** | 1 | `D3-15` | Extraction View fails to extract from bound text artifacts (passes empty text). |
| **HIGH** | 5 | `D3-01`, `D3-02`, `D3-08`, `D3-11`, `D3-16` | Broken WAI-ARIA tabpanels, missing accessible names on inputs, detached anchor downloads, PDF.js document memory leaks, and sync translation returning empty string on bound artifacts. |
| **MEDIUM** | 7 | `D3-03`, `D3-04`, `D3-05`, `D3-09`, `D3-12`, `D3-13`, `D3-17` | Ambiguous table action buttons, missing `aria-pressed` on processor chips, missing `aria-live` on async extractions, unsanitized export filenames, double-fire click bubbling in toggles, unplumbed `AbortSignal` in workstation polling, and in-memory config persistence 503 handling. |
| **LOW** | 4 | `D3-06`, `D3-07`, `D3-10`, `D3-14` | Bounding box tooltips hover-only, toggle focus-visible native checkbox visual glitch, query string token exposure, and misplaced Svelte 5 rune import. |

---

## Detailed Audit Findings

### [D3-15] CRITICAL: Extraction View Fails to Extract from Bound Text Artifacts
- **Location:** [`frontend/src/lib/components/views/ExtractionView.svelte:55-76`](file:///d:/OmniScribe/frontend/src/lib/components/views/ExtractionView.svelte#L55-L76), [`src/omniscribe/api/services/ai.py:209`](file:///d:/OmniScribe/src/omniscribe/api/services/ai.py#L209)
- **Impact**: When a document is loaded and the user initiates extraction without typing into the textarea, the request payload contains `text: ""` and `/api/extract` fails or returns empty fields because artifact IDs are not resolved on the extraction endpoint.
- **Fix**: Load text content from the bound artifact before submitting or accept `text_artifact_id` in `ExtractionRequest`.

---

### [D3-01] HIGH: Broken WAI-ARIA Tabpanel Pattern in Settings View
- **Location:** [`frontend/src/lib/components/views/SettingsView.svelte:162-177, 198, 283, 354, 400`](file:///d:/OmniScribe/frontend/src/lib/components/views/SettingsView.svelte#L162-L177)
- **WCAG**: 4.1.2 Name, Role, Value (Level A), 1.3.1 Info and Relationships (Level A)
- **Fix**: Wrap tab card containers in `role="tabpanel"` with matching `id` and `aria-labelledby`.

---

### [D3-02] HIGH: Unlabeled Form Controls Missing Accessible Names
- **Location:** [`ExtractionView.svelte:167`](file:///d:/OmniScribe/frontend/src/lib/components/views/ExtractionView.svelte#L167), [`TranslationView.svelte:273`](file:///d:/OmniScribe/frontend/src/lib/components/views/TranslationView.svelte#L273), [`TranscriptionView.svelte:176, 189`](file:///d:/OmniScribe/frontend/src/lib/components/views/TranscriptionView.svelte#L176)
- **WCAG**: 1.3.1, 4.1.2, 3.3.2
- **Fix**: Add explicit `<label>` or `aria-label` to textareas, audio player, and file inputs.

---

### [D3-08] HIGH: Detached Anchor Clicks and Immediate Revoke Leading to 0-Byte Downloads
- **Location:** [`TranscriptionView.svelte:98-125`](file:///d:/OmniScribe/frontend/src/lib/components/views/TranscriptionView.svelte#L98-L125), [`ExportModal.svelte:58-67`](file:///d:/OmniScribe/frontend/src/lib/components/views/ExportModal.svelte#L58-L67)
- **Fix**: Attach temporary `<a>` element to `document.body` before calling `.click()` and delay `URL.revokeObjectURL` via `setTimeout(..., 1000)`.

---

### [D3-11] HIGH: PDF.js Document Proxy & Worker Memory Leak
- **Location:** [`frontend/src/lib/utils/pdfPreview.ts:117-120, 174-218`](file:///d:/OmniScribe/frontend/src/lib/utils/pdfPreview.ts#L117-L120), [`PdfMiniViewer.svelte:117-120`](file:///d:/OmniScribe/frontend/src/lib/components/workstation/PdfMiniViewer.svelte#L117-L120)
- **Fix**: Call `pdfDoc?.destroy()` and `page.cleanup()` when reloading or switching documents.

---

### [D3-16] HIGH: Synchronous Translation Returns Empty String on Bound Artifacts
- **Location:** [`TranslationView.svelte:70-120`](file:///d:/OmniScribe/frontend/src/lib/components/views/TranslationView.svelte#L70-L120), [`src/omniscribe/api/services/ai.py:130`](file:///d:/OmniScribe/src/omniscribe/api/services/ai.py#L130)
- **Fix**: Fetch and populate source text before calling `/api/translate` or resolve artifact on backend.

---

### [D3-03] MEDIUM: Ambiguous Action Buttons in Glossary and Job History Tables
- **Location:** [`GlossaryView.svelte:209-236`](file:///d:/OmniScribe/frontend/src/lib/components/views/GlossaryView.svelte#L209-L236), [`JobHistoryView.svelte:169`](file:///d:/OmniScribe/frontend/src/lib/components/views/JobHistoryView.svelte#L169)
- **Fix**: Add contextual `aria-label={`Delete glossary ${glossary.id}`}`.

---

### [D3-04] MEDIUM: Missing `aria-pressed` on Processor Chips
- **Location:** [`SettingsView.svelte:256-276`](file:///d:/OmniScribe/frontend/src/lib/components/views/SettingsView.svelte#L256-L276)
- **Fix**: Add `aria-pressed={selectedProcessors.includes(proc)}` to toggle buttons.

---

### [D3-05] MEDIUM: Dynamic Loading States Missing `role="status"`
- **Location:** [`ExtractionView.svelte:211`](file:///d:/OmniScribe/frontend/src/lib/components/views/ExtractionView.svelte#L211), [`TranscriptionView.svelte:262`](file:///d:/OmniScribe/frontend/src/lib/components/views/TranscriptionView.svelte#L262)
- **Fix**: Add `role="status" aria-live="polite"` to loading spinners.

---

### [D3-09] MEDIUM: Unsanitized Export Filenames
- **Location:** [`ExportModal.svelte:78-123`](file:///d:/OmniScribe/frontend/src/lib/components/views/ExportModal.svelte#L78-L123)
- **Fix**: Sanitize special characters and path traversal before setting `a.download`.

---

### [D3-12] MEDIUM: Click Event Bubbling Double-Toggle in Custom Switches
- **Location:** [`ProcessSettings.svelte:126-170`](file:///d:/OmniScribe/frontend/src/lib/components/workstation/ProcessSettings.svelte#L126-L170), [`Toggle.svelte:20-53`](file:///d:/OmniScribe/frontend/src/lib/components/ui/Toggle.svelte#L20-L53)
- **Fix**: Remove redundant `onclick` handler from outer container when bound to `<input type="checkbox">`.

---

### [D3-13] MEDIUM: Missing `AbortSignal` in Workstation Polling
- **Location:** [`WorkstationView.svelte:127-148`](file:///d:/OmniScribe/frontend/src/lib/components/workstation/WorkstationView.svelte#L127-L148)
- **Fix**: Plumb `AbortSignal` into async polling loops and cancel on unmount.

---

### [D3-17] MEDIUM: In-Memory Backend 503 Config Persistence Error Toast
- **Location:** [`SettingsView.svelte:70-115`](file:///d:/OmniScribe/frontend/src/lib/components/views/SettingsView.svelte#L70-L115)
- **Fix**: Handle 503 gracefully with informational toast that settings are active for current session.

---

### [D3-06] LOW: Hover-Only Bounding Box Tooltips
- **Location:** [`PageCanvas.svelte:153-169`](file:///d:/OmniScribe/frontend/src/lib/components/workstation/PageCanvas.svelte#L153-L169)
- **Fix**: Add focus-visible tooltip triggers for keyboard accessibility.

---

### [D3-07] LOW: Toggle Native Checkbox Visible Overlay on Focus
- **Location:** [`Toggle.svelte:48-52`](file:///d:/OmniScribe/frontend/src/lib/components/ui/Toggle.svelte#L48-L52)
- **Fix**: Apply focus ring to custom track rather than making native input visible.

---

### [D3-10] LOW: Query Parameter Token Passing in `endpoints.ts`
- **Location:** [`endpoints.ts:117-119`](file:///d:/OmniScribe/frontend/src/lib/api/endpoints.ts#L117-L119)
- **Fix**: Use bearer headers instead of query parameters.

---

### [D3-14] LOW: Misplaced Svelte 5 Rune Import in Async Handler
- **Location:** [`GlossaryView.svelte:3, 104`](file:///d:/OmniScribe/frontend/src/lib/components/views/GlossaryView.svelte#L3)
- **Fix**: Use standard `URLSearchParams`.
