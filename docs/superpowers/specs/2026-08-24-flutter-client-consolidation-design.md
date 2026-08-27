# Flutter Client Consolidation — Design Spec

**Date:** 2026-08-24
**Status:** Approved (pending user review of this spec doc)
**Scope:** `client/` (Flutter desktop client) only. Backend Python and Svelte frontend are out of scope.

## 1. Goals & non-goals

### Goals (in scope)

1. Make `data/` (Stack A) the canonical domain layer; make `presentation/` the only UI layer; eliminate `state/`, `models/`, `repositories/`, `services/`, and `core/theme/` once nothing imports them.
2. Wire every `presentation/` screen through Riverpod `NotifierProvider`s that wrap `data/repositories/`.
3. Migrate **Settings** as the first vertical slice (proof of pattern on the heaviest domain types).
4. Configure Flutter Desktop (Windows first, Linux/macOS second) so the app builds and runs natively.
5. Keep `analysis_options.yaml` clean: no `avoid_relative_lib_imports` violations; `dart analyze` exits 0.

### Non-goals (explicitly out of scope)

1. Replacing the Svelte frontend today. The Flutter client and Svelte `frontend/` coexist; Flutter is the desktop path, Svelte is the web path.
2. Adding new product features. This design is consolidation + first slice only. Features (file-drop into workstation, native window controls, local persistence) are Phase 2.
3. Mobile (iOS/Android) targets. Desktop only.
4. Backward-compat shims. Once `state/` etc. have zero importers, delete them.
5. Touching the Svelte frontend or any backend Python code in this design.

## 2. Target folder structure (post-consolidation)

```
client/lib/
├── main.dart
├── core/                              # Cross-cutting infrastructure
│   ├── constants/api_constants.dart
│   ├── enums/{app_tab,server_health}.dart
│   ├── exceptions/api_exceptions.dart
│   ├── network/api_client.dart
│   └── websocket/ws_client.dart
├── data/                              # Domain layer (Riverpod-friendly)
│   ├── models/                        # Domain types — JSON ↔ Dart
│   │   ├── bbox_item.dart
│   │   ├── document_result.dart
│   │   ├── feature_models.dart
│   │   ├── job_record.dart
│   │   ├── process_settings.dart
│   │   ├── provider_preset.dart
│   │   └── ws_frames.dart
│   ├── repositories/                  # Abstract + impl pairs
│   │   ├── config_repository.dart
│   │   ├── feature_repository.dart
│   │   ├── job_repository.dart
│   │   ├── ocr_repository.dart
│   │   └── provider_repository.dart
│   └── providers/                     # Riverpod providers/notifiers (single source of truth)
│       ├── repository_providers.dart
│       ├── settings_notifier.dart     # NEW — Settings slice target
│       ├── provider_notifier.dart     # NEW — Provider Browser slice target
│       ├── job_notifier.dart          # NEW — Job History slice target
│       └── ...
├── presentation/                      # UI only — consumes Riverpod providers
│   ├── shell/app_shell.dart
│   ├── features/                      # Screen widgets, one per tab
│   ├── jobs/
│   ├── providers/
│   ├── settings/
│   ├── workstation/
│   └── widgets/                       # DocuVerse design-system widgets
└── theme/                             # DocuVerse design tokens
    ├── docuverse_colors.dart
    ├── docuverse_theme.dart
    └── docuverse_typography.dart
```

### Removed when their last importer migrates

- `lib/models/` (Stack B's simple DTOs — replaced by `data/models/`)
- `lib/repositories/` (Stack B's thin repos — replaced by `data/repositories/`)
- `lib/services/` (Stack B's `api_client.dart` — replaced by `core/network/api_client.dart`)
- `lib/state/` (Stack B's `ChangeNotifier` + `InheritedNotifier` state — replaced by `data/providers/*_notifier.dart`)
- `lib/core/theme/` (Stack A's orphaned theme — `theme/docuverse_theme.dart` already powers `main.dart`)
- `lib/presentation/common/` (Stack B's `app_*` widgets — replaced by `presentation/widgets/docuverse_*`)
- `lib/presentation/views/` (Stack B's `*_view.dart` — replaced by `presentation/features/*_screen.dart`)

### Key rules for the consolidated tree

1. All non-`package:` imports use `package:omniscribe_client/...` (the `analysis_options.yaml` `avoid_relative_lib_imports` rule is enforced; current `../../core/...` style is rewritten).
2. Every screen is a `ConsumerWidget` (or `ConsumerStatefulWidget`) that watches the Riverpod provider(s) for its slice. Each slice owns exactly one primary `NotifierProvider`; additional shared providers (e.g. `apiClientProvider`, `wsClientProvider`) may also be watched.
3. Notifier classes live in `data/providers/`; they extend `Notifier<T>` (the modern Riverpod 2.x API — `StateNotifier` is deprecated).
4. Repositories expose async methods; notifiers wrap them, expose immutable state via `copyWith`, and never call repositories directly from widgets.

## 3. Vertical-slice migration contract

### Per-slice recipe (4 steps)

1. **Provider in `data/providers/`** — Create (or extend) `<feature>_notifier.dart`. Define a `Notifier<FeatureState>`. Inject the matching `*Repository` from `repository_providers.dart`. Expose `featureStateProvider`.
2. **Screen rewrite** — Replace `presentation/features/<feature>_screen.dart` so it's a `ConsumerWidget` that does `ref.watch(featureStateProvider)`. Replace any direct repository / `ChangeNotifier` calls with `ref.read(notifier.notifier).someAction()`.
3. **Delete the old state files** — Remove `state/<feature>_provider.dart`, `state/<feature>_state.dart`, and any wrappers. Run `flutter analyze` and confirm zero new errors.
4. **Test** — Add or update one widget test in `client/test/` exercising the provider's reducer logic. Run `dart analyze`, `flutter test`, `flutter build windows --debug`. Commit.

### Slice ordering

| # | Slice | Repos / providers touched | State files removed |
|---|-------|---------------------------|---------------------|
| 1 | **Settings** | `ConfigRepository`, new `SettingsNotifier` | `state/config_provider.dart`, `state/config_state.dart`, `services/api_client.dart`, `models/config.dart` |
| 2 | **Provider Browser** | `ProviderRepository`, new `ProviderCatalogNotifier` | `state/provider_browser_provider.dart`, `state/provider_browser_state.dart` |
| 3 | **Job History** | `JobRepository`, new `JobsNotifier` (+ WebSocket wiring) | `state/jobs_provider.dart`, `state/jobs_state.dart`, `state/progress_provider.dart`, `state/progress_state.dart` |
| 4 | **Features screens** (Translation, Transcription, Glossary, Extraction) | `FeatureRepository`, per-feature notifiers | `state/features_provider.dart` |
| 5 | **Workstation** | `OcrRepository`, new `WorkstationNotifier` | `state/document_provider.dart`, `state/document_state.dart`, `models/document_view_model.dart`, `models/bbox_item.dart`, `models/page_result.dart`, `models/trust_summary.dart` |
| 6 | **Final cleanup** | n/a | Delete `lib/state/`, `lib/models/`, `lib/repositories/`, `lib/services/`, `lib/core/theme/`, `lib/presentation/common/`, `lib/presentation/views/` once empty |

### Slice invariants (every slice must satisfy)

- The slice's screen builds and runs against the live OmniScribe backend.
- `dart analyze` reports zero new issues introduced by the slice.
- The slice adds ≥1 widget test or notifier test in `client/test/`.
- No `// ignore: ...` lines added without justification.
- No new relative imports (`../../`) introduced; everything uses `package:omniscribe_client/...`.

## 4. Settings slice (first vertical slice) detail

### Why Settings first

It touches every domain type — `ProcessSettings`, `ConfigUpdate`, `RuntimeConfig`, `PipelineMode`, `DenseMode`, `SpellcheckMode`, `DocumentProcessorName` — and exercises fetch + mutate round-trips, optimistic state, and error surfaces. If Settings works, every later slice reuses the same shape.

### Files in scope for this slice

```
NEW:
  client/lib/data/providers/settings_notifier.dart
  client/lib/data/providers/settings_state.dart
  client/test/data/settings_notifier_test.dart

MODIFIED:
  client/lib/presentation/features/settings_screen.dart
  client/lib/main.dart   # No structural change; boot still works

DELETED (after slice 1 lands + zero importers):
  client/lib/state/config_provider.dart
  client/lib/state/config_state.dart
  client/lib/services/api_client.dart
  client/lib/models/config.dart
```

### `SettingsState` shape

Flat record with `copyWith` + equality:

```dart
@immutable
class SettingsState {
  const SettingsState({
    required this.isLoading,
    required this.runtimeConfig,        // RuntimeConfig? — null until first load() succeeds
    required this.activeProviderId,
    required this.ocrModels,
    required this.translationModels,
    required this.transcriptionModels,
    required this.serverBaseUrl,
    required this.useAsync,
    required this.error,
    required this.isDarkMode,
  });
  // copyWith + equality
}
```

### `SettingsNotifier` shape

```dart
final settingsStateProvider = NotifierProvider<SettingsNotifier, SettingsState>(
  SettingsNotifier.new,
);

class SettingsNotifier extends Notifier<SettingsState> {
  late final ConfigRepository _repo;

  @override
  SettingsState build() {
    _repo = ref.watch(configRepositoryProvider);
    return const SettingsState.initial();
  }

  Future<void> load() async { /* GET /api/config, GET /health, GET /api/providers/{id}/models */ }
  Future<void> updateConfig(ConfigUpdate update) async { /* POST /api/config */ }
  Future<void> updateOcr(ProcessSettings next) async { /* POST /api/config (ocr subset) */ }
  Future<void> updateTranslation(ProcessSettings next) async { /* ... */ }
  Future<void> updateTranscription(ProcessSettings next) async { /* ... */ }
  void setServerBaseUrl(String url) { /* mutates apiClient + re-fetches */ }
  void setAuthToken(String? token) { /* mutates apiClient + ref.read(authTokenProvider) */ }
  void setActiveProvider(String id) { /* local-only, used by shell badge */ }
  void toggleDarkMode([bool? force]) { /* local-only */ }
}
```

### Behavior preservation (Settings must not regress)

- Dark-mode toggle is local-only (no server round-trip), same as today.
- `setServerBaseUrl` mutates `ApiClient.baseUrl` and re-fetches config.
- `updateOcr` / `updateTranslation` / `updateTranscription` each do `POST /api/config` with the relevant subset, then re-fetch.
- Optimistic state for `useAsync` toggle (local-first, then `updateConfig`).
- Errors surface via `state.error` + `ref.listen` for toast emission. Toast overlay (`presentation/common/toast_overlay.dart`) is moved into `presentation/widgets/` first if not already there.

### Imports rewrite (Settings screen)

All `import '../../state/config_provider.dart';` etc. become `import 'package:omniscribe_client/data/providers/settings_notifier.dart';` etc. Same for any `import '../../models/config.dart';` — replaced with `data/models/process_settings.dart`.

### Tests

- `settings_notifier_test.dart` — using `ProviderContainer` (no Flutter binding), mock `ConfigRepository`, verify:
  - `load()` populates `runtimeConfig`, `ocrModels`, `translationModels`, `transcriptionModels`, `activeProviderId`, `isLoading=false`
  - `load()` failure populates `error` and clears `isLoading`
  - `updateOcr(ProcessSettings(...))` calls `repo.updateOcrConfig` with correct payload
  - `setServerBaseUrl` updates `apiClient.baseUrl` and re-triggers `load()`
  - `toggleDarkMode()` flips `isDarkMode` and does not hit the repo
- Optional: one widget test mounting `SettingsScreen` against an overridden `settingsStateProvider` and verifying the dark-mode toggle button works.

### Out of scope for this slice

- Per-section expand/collapse state (UI-only, no domain logic).
- Glossary import UI (Slice 4).
- File picker / save dialog wiring (Phase 2).

## 5. Post-consolidation feature roadmap (Phase 2 — out of scope for this design)

Sequenced list. None of this is in scope for the current design.

### Tier A — Desktop platform completeness

| # | Feature | Depends on |
|---|---------|------------|
| A1 | `flutter create --platforms=windows,linux,macos .` in `client/`; verify `flutter build windows --debug` produces a runnable `.exe`. Add `path_provider` dep. | Flutter SDK installed |
| A2 | File picker integration via `file_picker` (already in deps) into `upload_dropzone.dart`. | Slice 5 done |
| A3 | `desktop_drop` (already in deps) into `document_viewport.dart`. | A2 done |
| A4 | Local settings persistence via `shared_preferences`. | Slice 1 done |

### Tier B — Workstation UX parity with Svelte frontend

| # | Feature |
|---|---------|
| B1 | Bbox selection + page navigation |
| B2 | Async OCR + progress WebSocket |
| B3 | Trust panel |
| B4 | Process settings panel |
| B5 | Metadata panel + PDF mini-viewer |

### Tier C — Translation / Transcription / Glossary / Extraction

One slice each. Same `FeatureRepository` + per-feature `NotifierProvider` pattern as slice 1.

### Tier D — Native desktop polish

D1 window manager; D2 system tray + global hotkeys; D3 native notifications; D4 auto-update channel.

### Tier E — Svelte sunset plan

Separate design when Flutter desktop reaches Tier A + B + C parity.

### Recommendation

1. **A1** first (enable desktop platform + first `flutter build` succeeds on Windows).
2. **A2 + A3 + A4** together (minimum "you can pick a file, drop it, and OCR it" on desktop).
3. **B1–B5** (workstation parity with Svelte).
4. **Tier C** (port remaining feature screens).

## 6. Validation gates (what "done" means per slice)

### Per-slice gates

```bash
# 1. Static analysis — must exit 0
cd client && dart analyze

# 2. Format check — must exit 0
cd client && dart format --set-exit-if-changed lib test

# 3. Unit + widget tests — must pass
cd client && flutter test

# 4. Windows desktop debug build — must succeed (or Linux/macOS if that's your platform)
cd client && flutter build windows --debug
```

### First-time-only gate (before any slice)

```bash
flutter doctor -v
cd client && flutter pub get
cd client && flutter create --platforms=windows,linux,macos .
```

### Per-slice smoke test (manual)

1. Boot the backend: `uv run omniscribe-server --port 8000`.
2. Launch the Flutter desktop app: `cd client && flutter run -d windows`.
3. Navigate to the slice's screen.
4. Verify the screen renders the live data and any mutation round-trips correctly.
5. Toggle dark/light theme and confirm the slice's widgets follow the theme.

### Documentation gates

- Slice commit message: `feat(client): <slice name> slice — Riverpod NotifierProvider replaces state/<old>`.
- If a slice adds a public API, mention it in the commit body.
- `AGENTS.md` is updated once Tier A (desktop platform) lands, not per slice.

### Quality bar

- Zero new `// ignore: ...` lines without justification in the same commit.
- Zero new relative imports (`../../...`).
- One test added per slice.
- Slice diff < 600 lines net (excluding generated `.dart_tool/` and platform folders).

## 7. Risks, open questions, and explicit non-decisions

### Risks

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| R1 | Flutter SDK install fails on Windows (PATH, antivirus, .NET desktop SDK) | Medium | Document install steps; defer slice 2+ if `flutter doctor` fails; slice 1 can still proceed with `dart analyze` for static checks |
| R2 | `StateNotifierProvider` is deprecated in Riverpod 2.x; live code uses it | Medium | Slice 1 converts to `NotifierProvider` + `Notifier<T>` (the 2.x API). Documented in slice 1 |
| R3 | `data/repositories/` repositories may have bugs (they were never wired, never tested) | Medium | Each slice adds the first test for that repo's notifier |
| R4 | `WsClient` (WebSocket) interaction with the existing InheritedNotifier path | Medium | Slice 3 is where WebSocket gets first migrated; fix there |
| R5 | `avoid_relative_lib_imports: true` is currently violated by ~all imports | High (already broken) | Slice 1 includes an "imports pass" that rewrites all `../../...` to `package:omniscribe_client/...` |
| R6 | No platform folders yet (`windows/`, `linux/`, `macos/`). Desktop build won't work without `flutter create --platforms=...`. | High | Run `flutter create --platforms=windows,linux,macos .` in `client/` after Flutter SDK is installed and before slice 1's `flutter build windows --debug` smoke test |
| R7 | `models/document_view_model.dart` is used by `state/document_state.dart` — slice 5 must migrate both atomically | Medium | Slice 5 is documented as one atomic migration (notifier + state + 4 model files together) |
| R8 | Backend in flux — recent commits touched `plugins/health.py`, `plugins/ocr/plugin.py`, `plugins/providers.py`, `server.py`. API surface may shift before slice 2 | Low–Medium | Each slice builds against the live backend; if an API shape changes, fix the repo + notifier in the owning slice |
| R9 | Some Riverpod concepts (`StateNotifierProvider`, `AsyncNotifier`, `Notifier`) coexist in the codebase. Picking one is a sub-decision | Low | Slice 1 sets the convention: `NotifierProvider<NotifierClass, ImmutableState>` |
| R10 | Stale branch: `client/` is untracked, so a `git pull` could overwrite it | Low | Add `.gitignore` patterns + commit `client/` in a single branch before any new work |

### Open questions (explicit non-decisions for this design)

1. **Flutter SDK version target.** Pubspec specifies `flutter: ">=3.19.0"` and `dart: ">=3.3.0 <4.0.0"`. Pin to whatever `flutter doctor` reports locally; revisit if Dart 4 lands.
2. **Test framework.** `flutter_test` is in dev_deps. Add `mocktail` to dev_deps during slice 1.
3. **Logging.** No logger exists in `core/`. Add `package:logging` + a Riverpod-scoped logger provider. Defer to Tier A4.
4. **i18n.** Not needed for an internal desktop tool. Skip unless requested.
5. **CI for Flutter.** Not in scope today. Add as a Phase 2 task.

### Explicit non-decisions (we are NOT deciding these now)

- Whether Flutter replaces Svelte. (Coexist today; revisit after Tier C lands.)
- Whether Flutter ships mobile (iOS/Android). (Desktop only for this design.)
- Whether `frontend/` should be deleted. (No.)
- Whether to add i18n. (No.)
- Whether to add CI for Flutter. (No.)

## Appendix: codebase facts this design is grounded in

- 111 Dart files / 21,400 lines in `client/lib/` as of 2026-08-24.
- Folder sizes: `presentation/` 50 files / 12,506 lines; `data/` 15 / 3,303; `models/` 15 / 2,037; `core/` 11 / 1,813; `state/` 11 / 828; `theme/` 3 / 384; `repositories/` 4 / 357; `services/` 1 / 144.
- `lib/main.dart` boots `presentation/shell/app_shell.dart` + `state/config_provider.dart` + `theme/docuverse_theme.dart` inside a Riverpod `ProviderScope`.
- `lib/core/`, `lib/data/`, `lib/repositories/`, `lib/services/` (Stack A) have zero importers — fully orphaned but with substantive code.
- `lib/state/config_provider.dart` uses `StateNotifierProvider` (Riverpod 2.x deprecated API). Slice 1 converts it to `NotifierProvider`.
- `analysis_options.yaml` enables `strict-casts`, `strict-inference`, `strict-raw-types`, `avoid_relative_lib_imports`, and 30+ lints.
- Backend just landed Cordis-style plugin harness rebuild (2026-08-23). Svelte frontend `frontend/` is the production web UI today (30+ Svelte files, 52 TS files, 19 commits staged ahead of `origin/main`).
- Flutter SDK is **not installed** on this machine as of 2026-08-24. User has elected to install it first.