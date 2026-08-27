# Flutter Takeover — Phase A: Flutter Against Current Backend

> **For agentic workers:** This spec defines the Phase A cutover. Phase B (Svelte
> deletion) is a separate spec and is out of scope here.

**Date:** 2026-08-27
**Status:** Approved — ready for implementation plan
**Owner:** rahin2uddin

## Context

The Flutter client ([client/](file:///d:/OmniScribe/client)) is UI-complete and
architecturally unified per the
[2026-08-27 unification plan](file:///d:/OmniScribe/docs/superpowers/plans/2026-08-27-flutter-architecture-unification-and-parity.md).
A 2026-08-26 parity audit identified the remaining gaps that block the Flutter
client from being the canonical UI surface:

- Three Flutter client endpoints 404 against the current backend:
  `ConfigRepository.getModels(namespace:)` calls `/api/models/{namespace}`;
  `ProviderRepository.setActiveProvider` and `validateProvider` call
  `/api/providers/active` and `/api/providers/validate`, none of which are
  mounted (the `ProviderManager.set_active` method exists but is unbound to a
  route).
- The `AuthRequiredBanner` widget from the Svelte reference UI is missing; the
  settings screen's "Security & Auth" tab still labels it as
  `"Auth token UI deferred to slice 5"`.
- Two keyboard shortcuts called out in the unification plan are unbound:
  `Ctrl+O` (open file picker) and `Ctrl+Enter` (start OCR).
- The Flutter web build has not been verified alongside the Windows desktop
  primary target.

The deferred feature subsystems (translation, transcription, extraction,
export, glossary — 18 endpoints) are explicitly out of scope. Each is its own
spec/plan cycle.

## Goals (Phase A)

1. Wire the two missing provider-config routes so the Flutter Provider Modal's
   "Validate" and "Set active" actions work end-to-end.
2. Rewire the Flutter `ConfigRepository` to discover models via
   `/api/providers/{provider_id}/models` instead of the deprecated
   `/api/models/{namespace}` shape.
3. Add the `AuthRequiredBanner` widget for Svelte parity (no-op against the
   current unauthenticated backend; ready when the deferred auth middleware
   ships).
4. Bind the two missing `AppShell` keyboard shortcuts.
5. Configure and verify the Flutter web build alongside the Windows desktop
   primary build.

## Non-Goals (deferred to later slices)

- Translation / transcription / extraction / export / glossary harness wiring.
- The `OMNISCRIBE_AUTH_TOKEN` ASGI middleware.
- Flutter mobile platforms (iOS, Android).
- Promoting `_processSettings` from `WorkstationScreen` local state to a
  shared Riverpod provider (Ctrl+Enter uses
  `ProcessSettings.defaultSettings()` for Phase A).
- Serving the Flutter web bundle from `omniscribe-server` at `/`.
- **Phase B — Svelte frontend deletion** (separate spec).

## Architectural decisions (recorded)

- **Decomposition:** Three-or-more slices; brainstorm the Flutter+Svelte slice
  first.
- **Build target:** Flutter desktop (Windows primary; Linux/macOS supported) +
  Flutter web (preserve `localhost:8000` browser UX).
- **Auth banner:** Include for parity (no-op against current server).
- **E2E coverage:** Drop Playwright e2e (`e2e/test_ui.py`,
  `axe-playwright-python`) entirely.
- **Cutover strategy:** Two-PR phased cutover. Phase A ships Flutter wired up
  against the current backend (no Svelte touch); Phase B deletes Svelte.

---

## Backend changes (Phase A)

**File touched (additive only):**
[src/omniscribe/plugins/providers.py](file:///d:/OmniScribe/src/omniscribe/plugins/providers.py).

### New route — `POST /api/providers/active`

```python
class SetActiveProviderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    provider_id: str = Field(alias="providerId")
    api_base: str = Field(alias="apiBase")
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str


class SetActiveProviderResponse(BaseModel):
    status: Literal["ok"]
    provider_id: str
    api_base: str
    model: str
```

Handler delegates to an extended
`ProviderManager.set_active(provider_id, api_base, api_key, model)`. When
`api_key` is non-empty, the method also writes through to
`self._settings.llm_api_key` (mirrors the OCR plugin's `update_config`
write-through at [src/omniscribe/plugins/ocr/plugin.py:392-394](file:///d:/OmniScribe/src/omniscribe/plugins/ocr/plugin.py)).

### New route — `POST /api/providers/validate`

```python
class ValidateProviderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    provider_id: str = Field(alias="providerId")
    api_base: str = Field(alias="apiBase")
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None  # not used by the probe; kept for client parity


class ValidateProviderResponse(BaseModel):
    valid: bool
    model_count: int
    error: str | None = None
```

Handler delegates to a new `ProviderManager.validate(provider_id, api_base, api_key)`:

- If `provider_id` not in `PROVIDER_TEMPLATES` → `{valid: False, model_count: 0, error: "unknown provider"}`.
- Else `httpx.AsyncClient.get(f"{base}/models", headers=auth, timeout=self._timeout)`
  (or `/api/tags` for `ollama`).
- On `2xx` + parseable JSON → `{valid: True, model_count: len(models), error: None}`.
- On exception → `{valid: False, model_count: 0, error: str(exc)}`.

### Backward compatibility

- No existing route changes. The three currently-mounted routes
  (`GET /api/providers`, `GET /api/providers/{id}`,
  `GET /api/providers/{id}/models`) keep their shape.
- `ProviderManager.set_active(...)` signature widens (new optional kwarg).
  Existing call sites are unaffected (the method is currently dead code outside
  its own definition).

### Backend tests

Extend [tests/plugins/test_providers_plugin.py](file:///d:/OmniScribe/tests/plugins/test_providers_plugin.py):

- `test_set_active_route_writes_through_settings` — POST
  `/api/providers/active` → assert `settings.llm_api_base` / `llm_model` /
  `llm_api_key` updated.
- `test_set_active_route_with_omitted_api_key` — `api_key` absent → existing
  `settings.llm_api_key` unchanged.
- `test_validate_route_returns_model_count` — mock `httpx.AsyncClient.get` →
  200 with 3-model payload → `{valid: True, model_count: 3}`.
- `test_validate_route_handles_offline_provider` — mock 5xx → `{valid: False, error: "..."}`.
- `test_validate_route_unknown_provider` — `provider_id="bogus"` →
  `{valid: False, error: "unknown provider"}`.

---

## Flutter client changes (Phase A)

### 1. Rewire `ConfigRepository`

[client/lib/data/repositories/config_repository.dart](file:///d:/OmniScribe/client/lib/data/repositories/config_repository.dart) — split the namespace-based
`getModels` into:

- **`getModelsForProvider(String providerId)`** — hits
  `/api/providers/{providerId}/models`, parses the `models[]` array, returns
  `List<String>`. Returns `const []` if the response shape is unexpected
  (matches Svelte's resilient pattern).
- **`getModels({String namespace = 'general'})`** — kept for back-compat with
  the existing call site in
  [client/lib/data/providers/settings_notifier.dart](file:///d:/OmniScribe/client/lib/data/providers/settings_notifier.dart).
  Internally delegates: `ocr` →
  `getModelsForProvider(state.activeProviderId)`; `translation` /
  `transcription` → return `const []` (deferred per harness rebuild spec);
  `general` → `getModelsForProvider('lmstudio')` fallback.

[client/lib/data/providers/settings_notifier.dart](file:///d:/OmniScribe/client/lib/data/providers/settings_notifier.dart)
— `load()` passes `state.activeProviderId` directly:

```dart
final ocrModels = await _repo.getModelsForProvider(state.activeProviderId);
final translationModels = <String>[];   // deferred per harness rebuild spec
final transcriptionModels = <String>[]; // deferred per harness rebuild spec
```

### 2. `ProviderRepository` alignment

The repository methods already exist with the correct request shapes. The
backend's Pydantic models use `ConfigDict(populate_by_name=True)` with field
aliases (camelCase ↔ snake_case) so the existing client JSON payloads parse
without changes. Client-side additions: verify the new round-trip in tests;
no other repository code changes.

### 3. `AuthRequiredBanner` widget

**New file:**
[client/lib/presentation/common/auth_required_banner.dart](file:///d:/OmniScribe/client/lib/presentation/common/auth_required_banner.dart).

**State:** new Riverpod `StateProvider<bool> authRequiredProvider` in
[client/lib/data/providers/repository_providers.dart](file:///d:/OmniScribe/client/lib/data/providers/repository_providers.dart).

**Behavior:**
- `false` (default) → renders `SizedBox.shrink()`.
- `true` → renders a dismissible banner matching the Svelte
  `AuthRequiredBanner.svelte` design:
  - `role="status"`, `aria-live="polite"`.
  - Warning icon + "Authentication required — the API rejected the request with a 401. Set a bearer token in Settings to continue."
  - **Open Settings** button → sets `activeTabProvider = AppTab.settings`,
    clears `authRequiredProvider`.
  - **Dismiss** (×) icon button → clears `authRequiredProvider`.

**Mount point:** [client/lib/presentation/shell/app_shell.dart](file:///d:/OmniScribe/client/lib/presentation/shell/app_shell.dart) — wrap the
`TabRibbon` in a `Column` and insert the banner as the first child.

**Trigger plumbing:** add an `onUnauthorized` callback parameter to
[client/lib/core/network/api_client.dart](file:///d:/OmniScribe/client/lib/core/network/api_client.dart).
The factory in `repository_providers.dart` wires it to
`() => ref.read(authRequiredProvider.notifier).state = true`. Each
`_apiClient.get / post / postMultipart / getBytes` already centralizes
`DioException` handling; add
`if (e.response?.statusCode == 401) onUnauthorized?.call();` before rethrow.

### 4. `AppShell` keyboard shortcuts

Add two bindings to the existing `CallbackShortcuts` map in
[client/lib/presentation/shell/app_shell.dart](file:///d:/OmniScribe/client/lib/presentation/shell/app_shell.dart):

- **Ctrl+O** — only fires when `activeTab == AppTab.workstation`. Increments
  `WorkstationState.filePickSignal` (new int field, default 0). The existing
  [client/lib/presentation/workstation/controls/upload_dropzone.dart](file:///d:/OmniScribe/client/lib/presentation/workstation/controls/upload_dropzone.dart)
  gains `ref.listen<int>(workstationProvider.select((s) => s.filePickSignal), (prev, next) { if (next > (prev ?? 0)) _pickFile(); })`.
- **Ctrl+Enter** — only fires when `activeTab == AppTab.workstation` AND
  `wsState.hasDocument`. Calls new `WorkstationNotifier.processCurrentDocument()`
  which delegates to
  `processOcrSync(settings: ProcessSettings.defaultSettings())`.

### 5. Flutter web build configuration

- Verify [client/web/](file:///d:/OmniScribe/client/web) directory exists
  (from prior `flutter create`). If not, run
  `flutter create --platforms=web .` (additive only; doesn't disturb existing
  platforms).
- No `pubspec.yaml` dependency changes expected — desktop/web builds share
  the same deps.
- Add `client/scripts/build_web.sh` helper for `flutter build web --release`
  (manual verification only for this slice; not in CI gate).
- [start_app.vbs](file:///d:/OmniScribe/start_app.vbs) launcher stays
  unchanged in Phase A — boots FastAPI; serving the Flutter web bundle from
  the server is a Phase B concern.

### 6. Settings screen cleanup

- Remove the `"Auth token UI deferred to slice 5"` badge from
  `_buildSecurityAuthTab`. Replace with a neutral `AppBadge` reading
  `"Auth middleware deferred — settings have no effect today"`.

---

## Verification gates

### Backend gate

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
uv run pytest tests/plugins/test_providers_plugin.py -v
```

### Flutter gate

```bash
cd client
flutter analyze
flutter test
flutter build windows --debug
flutter build web --release
```

### Acceptance criteria

1. `GET /api/providers` returns the same shape it does today (no regression).
2. `POST /api/providers/active` with `{providerId, apiBase, model}` → 200
   `{status: "ok", ...}` and `RuntimeSettings.llm_api_base` / `llm_model`
   are updated.
3. `POST /api/providers/validate` against an unreachable endpoint → 200
   `{valid: False, error: "<reason>"}`.
4. `POST /api/providers/validate` against `lmstudio` (if running) → 200
   `{valid: True, modelCount: N}`.
5. The Phase A changes do **not** alter the response shape of any other
   mounted route.
6. `flutter test` passes with new widget tests added (auth banner, shortcuts).
7. `flutter analyze` reports 0 issues.
8. Windows debug build produces a runnable executable.
9. Web release build produces `client/build/web/index.html` + assets without
   errors.
10. Manual smoke against a running FastAPI server:
    - Settings screen loads OCR models via `/api/providers/{id}/models`.
    - Provider modal "Validate" surfaces the result.
    - Provider modal "Set active" updates the server's runtime config.
    - On Workstation tab, `Ctrl+O` opens the file picker; `Ctrl+Enter` starts
      OCR.
    - `AuthRequiredBanner` never appears against the current unauthenticated
      server.

---

## Phase B preview (separate spec)

Mechanical deletion sweep. Touches (delete or update):

- `frontend/` directory (full deletion).
- `.github/workflows/test.yml` — remove the `frontend` and `e2e` jobs; keep
  `lint`, `test`, `nightly`, `windows-build`.
- `pyproject.toml` — drop `axe-playwright-python` from `[dependency-groups] dev`.
- `install.sh` / `install.bat` / `install.ps1` / `start_app.vbs` — drop
  Node/Vite install steps.
- `Dockerfile` / `compose.yaml` — drop Vite build stage / frontend service.
- `AGENTS.md` / `README.md` / `ARCHITECTURE.md` / `DEPLOYMENT.md` /
  `SECURITY.md` — remove Svelte references; update the peripheral-validation
  table; replace the "Windows quick-start" instructions.
- `.pre-commit-config.yaml` / `.gitignore` — drop frontend-specific entries.

Verification: full backend fast gate + Flutter gate (Windows + web).