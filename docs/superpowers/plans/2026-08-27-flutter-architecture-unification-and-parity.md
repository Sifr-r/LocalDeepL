# Flutter Architecture Unification & Feature Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify the OmniScribe Flutter client architecture according to [flutter-apply-architecture-best-practices](../../../C:/Users/rahin/.gemini/config/plugins/flutter/skills/flutter-apply-architecture-best-practices/SKILL.md), eliminate duplicated UI/theme systems (`docuverse_*` vs `app_*`), encapsulate presentation side-effects into Riverpod 2.x `Notifier`s, and close remaining feature parity gaps with the reference Svelte UI (Export Modal, Trust Breakdown Panel, Desktop Keyboard Shortcuts, and Auth Banner).

**Architecture:**

- **UI Layer (Presentation):** Lean, accessible views listening to Riverpod 2.x `Notifier`s. State mutations, async polling timers, and audio playback simulations are strictly encapsulated in `data/providers/*_notifier.dart` rather than widget state.
- **Component Suite & Design System:** 100% unified on `lib/core/theme/` (`AppTheme`, `AppColorScheme`, `AppTypography`) and `lib/presentation/common/` (`app_button.dart`, `app_badge.dart`, `app_card.dart`, `app_input.dart`, `app_modal.dart`, `app_select.dart`, `app_toggle.dart`, `section_header.dart`, `toast_service.dart`). Legacy `lib/theme/` and `lib/presentation/widgets/` are completely purged.
- **Navigation Shell:** `AppShell` delegates header navigation and real-time backend latency monitoring to canonical `TabRibbon` and `ServerHealthBadge`.
- **Data & Service Layer:** Repositories consume stateless API clients (`ApiClient`, `WsClient`) and return typed models (`DocumentResult`, `JobRecord`, `ProcessSettings`, `FeatureModels`).

**Tech Stack:** Flutter 3.24+ (Windows desktop primary), Dart 3.3+, `flutter_riverpod ^2.5.1` (`Notifier` / `NotifierProvider`), `dio ^5.4.3+1`, `web_socket_channel ^3.0.0`, `mocktail ^1.0.4`, `flutter_test`.

---

## File Structure

### Files to create

| Path | Purpose |
| :--- | :--- |
| `client/lib/presentation/workstation/modals/export_modal.dart` | Multi-format document export modal (Searchable PDF, DOCX, DOCX Tree, HTML, Tree JSON, Markdown, Text) |
| `client/lib/presentation/workstation/controls/trust_breakdown_panel.dart` | Deep-dive trust & calibration metrics panel (Platt calibration, OCR trust score, Hallucination risk, Script confidence, Block retry stats) |
| `client/test/presentation/export_modal_test.dart` | Widget and interaction tests for `ExportModal` |
| `client/test/presentation/trust_breakdown_panel_test.dart` | Widget tests for trust score calculations and calibration visualizer |

### Files to modify

| Path | Change |
| :--- | :--- |
| `client/lib/main.dart` | Switch from `DocuVerseTheme` to `AppTheme.darkTheme` / `AppTheme.lightTheme` |
| `client/lib/presentation/shell/app_shell.dart` | Integrate `TabRibbon` and bind global keyboard shortcuts (`Ctrl+O`, `Ctrl+Enter`, `Ctrl+S`, `Ctrl+1..7`) |
| `client/lib/presentation/features/translation_screen.dart` | Re-skin to `app_*` widgets + `context.colors`; move polling loop into `TranslationNotifier` |
| `client/lib/presentation/features/transcription_screen.dart` | Re-skin to `app_*` widgets + `context.colors`; move playback timer into `TranscriptionNotifier` |
| `client/lib/presentation/features/glossary_screen.dart` | Re-skin to `app_*` widgets + `context.colors`; extract inline modal into reusable controller |
| `client/lib/presentation/features/extraction_screen.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/settings/settings_screen.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/providers/provider_modal.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/providers/provider_card.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/workstation_screen.dart` | Re-skin to `app_*` widgets; mount Export button and Trust modal trigger |
| `client/lib/presentation/workstation/canvas/bbox_inspector.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/canvas/document_viewport.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/controls/page_strip.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/controls/quality_repair_dock.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/controls/right_control_dock.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/controls/upload_dropzone.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/workstation/progress/bottom_progress_dock.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/presentation/shell/workspace_view.dart` | Re-skin to `app_*` widgets + `context.colors` |
| `client/lib/data/providers/features_notifier.dart` | Add stateful polling and audio playback timer management |
| `client/lib/data/providers/features_state.dart` | Add audio playback position and async polling status fields |

### Files to delete (after zero importers remain)

| Path | Replaced by |
| :--- | :--- |
| `client/lib/theme/docuverse_colors.dart` | `client/lib/core/theme/app_colors.dart` |
| `client/lib/theme/docuverse_theme.dart` | `client/lib/core/theme/app_theme.dart` |
| `client/lib/theme/docuverse_typography.dart` | `client/lib/core/theme/app_typography.dart` |
| `client/lib/presentation/widgets/docuverse_badge.dart` | `client/lib/presentation/common/app_badge.dart` |
| `client/lib/presentation/widgets/docuverse_button.dart` | `client/lib/presentation/common/app_button.dart` |
| `client/lib/presentation/widgets/docuverse_card.dart` | `client/lib/presentation/common/app_card.dart` |
| `client/lib/presentation/widgets/docuverse_input.dart` | `client/lib/presentation/common/app_input.dart` |
| `client/lib/presentation/widgets/docuverse_modal.dart` | `client/lib/presentation/common/app_modal.dart` |
| `client/lib/presentation/widgets/docuverse_section_header.dart` | `client/lib/presentation/common/section_header.dart` |
| `client/lib/presentation/widgets/docuverse_select.dart` | `client/lib/presentation/common/app_select.dart` |
| `client/lib/presentation/widgets/docuverse_slider.dart` | `client/lib/presentation/common/app_slider.dart` (or standard SliderTheme) |
| `client/lib/presentation/widgets/docuverse_toggle.dart` | `client/lib/presentation/common/app_toggle.dart` |

---

## Phase 1: Theme & AppShell Header Unification

Align the application entry point and main shell with the canonical `AppTheme` and `TabRibbon`.

- [ ] **Step 1.1: Migrate `main.dart` to `AppTheme`**
  - Open `client/lib/main.dart`.
  - Replace `DocuVerseTheme.lightTheme` and `DocuVerseTheme.darkTheme` with `AppTheme.lightTheme` and `AppTheme.darkTheme`.
  - Verify that `ThemeMode` switches seamlessly between light and dark palettes.

- [ ] **Step 1.2: Refactor `AppShell` to mount `TabRibbon`**
  - Open `client/lib/presentation/shell/app_shell.dart`.
  - Remove the inline custom header container (which duplicated navigation tabs, logo, and static health badge).
  - Mount `const TabRibbon()` at the top of `AppShell`.
  - Bind `activeTabProvider` to switch between `screens[activeTab.index]`.

- [ ] **Step 1.3: Verify AppShell Navigation Tests**
  - Run `flutter test test/presentation/app_shell_test.dart` and ensure all tab switching tests pass.

---

## Phase 2: Secondary Screens Component Migration

Migrate the feature screens (`TranslationScreen`, `GlossaryScreen`, `TranscriptionScreen`, `ExtractionScreen`, `SettingsScreen`) to canonical `app_*` widgets and `context.colors`.

- [ ] **Step 2.1: Migrate `TranslationScreen`**
  - Replace all `DocuVerseCard`, `DocuVerseButton`, `DocuVerseToggle`, `DocuVerseBadge`, `DocuVerseSectionHeader` with `AppCard`, `AppButton`, `AppToggle`, `AppBadge`, `SectionHeader`.
  - Replace `context.docuVerse` with `context.colors` and `AppTypography`.

- [ ] **Step 2.2: Migrate `GlossaryScreen`**
  - Replace all `DocuVerse*` widgets with `App*` widgets.
  - Refactor `_showImportModal` to use `AppModal.show(...)` and `AppInput` / `AppSelect`.

- [ ] **Step 2.3: Migrate `TranscriptionScreen`**
  - Replace `DocuVerseCard`, `DocuVerseButton`, `DocuVerseBadge`, `DocuVerseInput`, `DocuVerseSectionHeader` with `AppCard`, `AppButton`, `AppBadge`, `AppInput`, `SectionHeader`.
  - Re-theme waveform slider to use `context.colors.brand`.

- [ ] **Step 2.4: Migrate `ExtractionScreen`**
  - Replace `DocuVerse*` widgets with `App*` widgets.
  - Apply `AppCard` and `AppButton` to template switcher and JSON AST output pane.

- [ ] **Step 2.5: Migrate `SettingsScreen`**
  - Replace `DocuVerse*` widgets across all four tabs (`General & Server`, `OCR Pipeline`, `Translation & Voice`, `Security & Auth`).

- [ ] **Step 2.6: Migrate `ProviderModal` and `ProviderCard`**
  - Replace all `DocuVerse*` widgets in `client/lib/presentation/providers/`.

---

## Phase 3: Workstation View & Sub-docks Migration

Migrate the primary OCR Workstation and its GPU viewport components to the unified design system.

- [ ] **Step 3.1: Migrate `WorkstationScreen` & Header**
  - Replace `DocuVerseBadge`, `DocuVerseButton`, and `context.docuVerse` tokens with `AppBadge`, `AppButton`, `context.colors`.

- [ ] **Step 3.2: Migrate Workstation Canvas (`DocumentViewport`, `BBoxInspector`)**
  - Update `BBoxPainter` and `DocumentViewport` to consume `AppColorScheme` from `context.colors`.
  - Update `BBoxInspector` to use `AppCard`, `AppBadge`, `AppButton`, `AppInput`, and `SectionHeader`.

- [ ] **Step 3.3: Migrate Workstation Controls (`RightControlDock`, `QualityRepairDock`, `PageStrip`, `UploadDropzone`)**
  - Update `RightControlDock` to use `AppSelect`, `AppCard`, `AppButton`, `SectionHeader`.
  - Update `QualityRepairDock` to use `AppCard`, `AppToggle`, `AppBadge`.
  - Update `PageStrip` and `UploadDropzone` to use `context.colors`.

- [ ] **Step 3.4: Migrate `BottomProgressDock`**
  - Update stage stepper, animated progress bar, and metrics pills to consume `context.colors`.

---

## Phase 4: Legacy Subsystem Purge & Fast Gate Verification

Remove the deprecated `docuverse_*` files and verify zero compiler or test regressions.

- [x] **Step 4.1: Delete `lib/theme/`**
  - Delete `client/lib/theme/docuverse_colors.dart`.
  - Delete `client/lib/theme/docuverse_theme.dart`.
  - Delete `client/lib/theme/docuverse_typography.dart`.

- [x] **Step 4.2: Delete `lib/presentation/widgets/`**
  - Delete `client/lib/presentation/widgets/` directory.

- [x] **Step 4.3: Run Static Analysis**
  - Run `flutter analyze` from `client/` and confirm **0 issues found**.

- [x] **Step 4.4: Run Test Suite**
  - Run `flutter test` and confirm all 174+ tests pass.

---

## Phase 5: Notifier Logic Isolation (ViewModel Purity)

Encapsulate presentation side-effects (timers and polling) inside Riverpod `Notifier` classes in accordance with [flutter-apply-architecture-best-practices](../../../C:/Users/rahin/.gemini/config/plugins/flutter/skills/flutter-apply-architecture-best-practices/SKILL.md).

- [x] **Step 5.1: Encapsulate Translation Polling in `TranslationNotifier`**
  - Move `Timer.periodic` polling logic from `_TranslationScreenState` into `TranslationNotifier.pollTranslationJob(String jobId)`.
  - Cancel timer on `ref.onDispose` within `TranslationNotifier`.
  - Update `TranslationScreen` to observe `state.isTranslating` and `state.asyncStatus`.

- [x] **Step 5.2: Encapsulate Transcription Audio Playback in `TranscriptionNotifier`**
  - Move `_playbackTimer` from `_TranscriptionScreenState` into `TranscriptionNotifier.startPlayback()` and `pausePlayback()`.
  - Expose `currentPlaybackTime` and `isPlaying` directly through `TranscriptionState`.

- [x] **Step 5.3: Add Unit Tests for Notifier Timers**
  - Add tests in `test/data/features_notifier_test.dart` verifying timer cancellation and state updates.

---

## Phase 6: Workstation Feature-Parity Extensions

Implement the missing user-facing capabilities present in the reference Svelte UI.

- [x] **Step 6.1: Implement `ExportModal`**
  - Create `client/lib/presentation/workstation/modals/export_modal.dart`.
  - Support export format selection: Searchable PDF, DOCX, DOCX Tree, HTML, Tree JSON, Markdown, Raw Text.
  - Wire modal to `FeatureRepository` (`exportDocx`, `exportHtml`, `exportDocxTree`, `exportBlockTree`).
  - Add an "Export" action button in `WorkstationScreen` header.

- [x] **Step 6.2: Implement `TrustBreakdownPanel`**
  - Create `client/lib/presentation/workstation/controls/trust_breakdown_panel.dart`.
  - Surface Platt calibrated trust score, OCR confidence, hallucination risk assessment, script detection, and block repair statistics.
  - Wire into `WorkstationScreen` alongside `BBoxInspector`.

- [x] **Step 6.3: Implement Global Keyboard Shortcuts**
  - In `AppShell`, wrap the body in a `Shortcuts` and `Actions` widget.
  - Bind:
    - `Ctrl+O`: Trigger file picker in dropzone
    - `Ctrl+Enter`: Start OCR processing
    - `Ctrl+S`: Open Export Modal
    - `Ctrl+0`: Reset canvas zoom (100%)
    - `Ctrl+1` through `Ctrl+7`: Switch navigation tabs

---

## Phase 7: Verification & Windows Native Build Gate

- [x] **Step 7.1: Comprehensive Unit & Widget Test Gate**
  - Run:
    ```powershell
    flutter test
    ```
  - Confirm all unit, state, repository, and widget tests pass.

- [x] **Step 7.2: Static Lint Gate**
  - Run:
    ```powershell
    flutter analyze
    ```
  - Confirm **0 warnings, 0 errors**.

- [x] **Step 7.3: Windows Desktop Native Build Gate**
  - Run:
    ```powershell
    flutter build windows --debug
    ```
  - Verify that the native executable compiles cleanly.

- [x] **Step 7.4: Ledger Sync**
  - Update `ARCHITECTURE.md` with the new file ledger and single responsibility mapping.

---

_Follow-up: [2026-08-27-flutter-takeover-phase-a](../plans/2026-08-27-flutter-takeover-phase-a.md) closes the remaining Flutter↔backend wiring (provider-config routes, auth banner, shortcuts, web build) ahead of Phase B Svelte deletion._
