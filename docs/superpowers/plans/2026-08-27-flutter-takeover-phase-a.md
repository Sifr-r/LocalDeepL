# Flutter Takeover Phase A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the Flutter client against the current backend so it is a fully-functional UI surface (with mock-fallback notifiers for deferred feature subsystems), then verify the Flutter web build alongside the Windows desktop primary target. Phase B (Svelte deletion) is a separate plan.

**Architecture:** Phase A is purely additive — two new provider-config routes on the harness, four Flutter client changes (config rewiring, auth banner, shortcuts, web build verification), and minimal state-notifier additions for keyboard-shortcut signal plumbing. No backend feature subsystem is rewired in this slice; the deferred endpoints keep their current 404 shape and the Flutter notifiers continue to fall back to mock data on those calls.

**Tech Stack:** FastAPI + Pydantic v2 + httpx (backend); Flutter 3.24+ / Dart 3.3+ / flutter_riverpod 2.5 / dio 5.4 (Flutter); pytest (backend tests); flutter_test + mocktail (Flutter tests).

---

## File Structure

### Files to create

| Path | Purpose |
|---|---|
| `client/lib/presentation/common/auth_required_banner.dart` | Dismissible banner matching the Svelte `AuthRequiredBanner.svelte` design (no-op against the current unauthenticated server) |
| `client/scripts/build_web.sh` | Manual `flutter build web --release` helper |
| `client/test/presentation/auth_required_banner_test.dart` | Widget tests for banner show/hide/dismiss |

### Files to modify

| Path | Change |
|---|---|
| `src/omniscribe/plugins/providers.py` | Add `POST /api/providers/active` and `POST /api/providers/validate` routes; extend `ProviderManager.set_active` with `api_key` kwarg; add `ProviderManager.validate` method; new Pydantic request/response models |
| `tests/plugins/test_providers_plugin.py` | Extend with five new route tests |
| `client/lib/data/providers/repository_providers.dart` | Add `authRequiredProvider = StateProvider<bool>` |
| `client/lib/core/network/api_client.dart` | Add `onUnauthorized` callback param; call it on Dio 401 in every method |
| `client/lib/presentation/shell/app_shell.dart` | Mount `AuthRequiredBanner` above `TabRibbon`; bind `Ctrl+O` and `Ctrl+Enter` |
| `client/lib/data/repositories/config_repository.dart` | Split `getModels` into `getModelsForProvider` + back-compat `getModels` |
| `client/lib/data/providers/settings_notifier.dart` | `load()` calls `getModelsForProvider(state.activeProviderId)`; translation/transcription hard-empty |
| `client/lib/data/providers/workstation_state.dart` | Add `filePickSignal` int field (default 0) |
| `client/lib/data/providers/workstation_notifier.dart` | Add `processCurrentDocument()` and `incrementFilePick()` methods |
| `client/lib/presentation/workstation/controls/upload_dropzone.dart` | Add `ref.listen` on `filePickSignal` to trigger file picker |
| `client/lib/presentation/settings/settings_screen.dart` | Replace "Auth token UI deferred to slice 5" badge with honest "Auth middleware deferred" message |

### Tests to extend

| Path | Additions |
|---|---|
| `client/test/data/config_repository_test.dart` | New tests for `getModelsForProvider` happy + parse-resilience + 404 paths |
| `client/test/data/settings_notifier_test.dart` | New tests for `load()` namespace mapping |
| `client/test/presentation/app_shell_test.dart` | New tests for Ctrl+O / Ctrl+Enter bindings |
| `client/test/data/workstation_notifier_test.dart` | New tests for `processCurrentDocument` + `incrementFilePick` |

---

## Phase 1 — Backend: Provider-Config Routes

### Task 1: Add `POST /api/providers/active` route

**Files:**
- Modify: `src/omniscribe/plugins/providers.py:1-296`
- Test: `tests/plugins/test_providers_plugin.py` (extend)

- [ ] **Step 1.1: Add the Pydantic models at the top of `providers.py` (above `PROVIDER_TEMPLATES`)**

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

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

- [ ] **Step 1.2: Extend `ProviderManager.set_active(...)` to accept an `api_key` kwarg**

Locate the `set_active` method on `ProviderManagerImpl` (search for `def set_active(` in `providers.py`). Replace it with:

```python
def set_active(
    self,
    *,
    provider_id: str | None = None,
    api_base: str,
    model: str,
    api_key: str | None = None,
) -> dict[str, str]:
    self._settings.llm_api_base = api_base
    self._settings.llm_model = model
    if api_key:
        self._settings.llm_api_key = api_key
    if provider_id:
        config = PROVIDER_TEMPLATES.get(provider_id)
        if config is not None and not api_base:
            self._settings.llm_api_base = config.api_url
    return self.get_active()
```

- [ ] **Step 1.3: Add the `POST /api/providers/active` route inside `build_providers_router`**

Append (before the `return router` line) inside `build_providers_router(manager: ProviderManagerImpl) -> APIRouter`:

```python
    @router.post("/active", status_code=200)
    async def set_active(payload: SetActiveProviderRequest) -> SetActiveProviderResponse:
        manager.set_active(
            provider_id=payload.provider_id,
            api_base=payload.api_base,
            model=payload.model,
            api_key=payload.api_key,
        )
        return SetActiveProviderResponse(
            status="ok",
            provider_id=payload.provider_id,
            api_base=payload.api_base,
            model=payload.model,
        )
```

- [ ] **Step 1.4: Write the failing route tests in `tests/plugins/test_providers_plugin.py`**

If the file does not exist, create it with the harness + `api_client` fixture from `tests/conftest.py`. Otherwise append two new tests:

```python
async def test_set_active_route_writes_through_settings(api_client):
    response = await api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
            "apiKey": "sk-test-1234",
            "model": "allenai/olmocr-2-7b",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providerId"] == "lmstudio"
    # Boot settings are seeded by the api_client fixture; assert write-through.
    runtime = await api_client.get("/api/providers")
    assert runtime.status_code == 200


async def test_set_active_route_with_omitted_api_key(api_client):
    # First write a sentinel api_key.
    await api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
            "apiKey": "sk-sentinel",
            "model": "allenai/olmocr-2-7b",
        },
    )
    # Now post without api_key; sentinel must be unchanged.
    response = await api_client.post(
        "/api/providers/active",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:9999/v1",
            "model": "different-model",
        },
    )
    assert response.status_code == 200
```

Adjust fixture names to match whatever `tests/conftest.py` ships under `tests/plugins/`. If the file uses a different pattern, mirror the existing test style — do not invent a new fixture contract.

- [ ] **Step 1.5: Run the new tests**

Run: `uv run pytest tests/plugins/test_providers_plugin.py -v`
Expected: 2 new tests PASS.

- [ ] **Step 1.6: Run the backend fast gate**

Run:
```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```
Expected: PASS, 0 ruff/mypy issues, all tests green.

- [ ] **Step 1.7: Commit**

```bash
git add src/omniscribe/plugins/providers.py tests/plugins/test_providers_plugin.py
git commit -m "feat(providers): add POST /api/providers/active route"
```

### Task 2: Add `POST /api/providers/validate` route

**Files:**
- Modify: `src/omniscribe/plugins/providers.py`
- Test: `tests/plugins/test_providers_plugin.py` (extend)

- [ ] **Step 2.1: Add `ValidateProviderRequest` and `ValidateProviderResponse` next to the `SetActive*` models**

```python
class ValidateProviderRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    provider_id: str = Field(alias="providerId")
    api_base: str = Field(alias="apiBase")
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None


class ValidateProviderResponse(BaseModel):
    valid: bool
    model_count: int
    error: str | None = None
```

- [ ] **Step 2.2: Add `ProviderManager.validate(...)` method to `ProviderManagerImpl`**

Add right after `set_active`:

```python
async def validate(
    self,
    provider_id: str,
    *,
    api_base: str,
    api_key: str | None = None,
) -> ValidateProviderResponse:
    config = PROVIDER_TEMPLATES.get(provider_id)
    if config is None:
        return ValidateProviderResponse(
            valid=False, model_count=0, error="unknown provider"
        )
    fallback = list(config.models)
    base = (api_base or config.api_url or "").rstrip("/")
    if not base:
        return ValidateProviderResponse(
            valid=False, model_count=0, error="no base URL for provider"
        )
    url = f"{base}/api/tags" if provider_id == "ollama" else f"{base}/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        client = self._client or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            payload = response.json()
        finally:
            if self._client is None:
                await client.aclose()
        if provider_id == "ollama":
            models = [str(entry["name"]) for entry in payload.get("models", [])]
        else:
            models = [str(entry["id"]) for entry in payload.get("data", [])]
        return ValidateProviderResponse(
            valid=True, model_count=len(models or fallback), error=None
        )
    except Exception as exc:
        _LOGGER.warning("validate failed for %s: %s", provider_id, exc)
        return ValidateProviderResponse(
            valid=False, model_count=0, error=str(exc)
        )
```

Add `from __future__ import annotations` is already at the top of the file; Pydantic models can sit at module scope above `PROVIDER_TEMPLATES` to keep their definitions co-located.

- [ ] **Step 2.3: Add the `POST /api/providers/validate` route**

Append inside `build_providers_router` (before `return router`):

```python
    @router.post("/validate", status_code=200)
    async def validate_provider(payload: ValidateProviderRequest) -> ValidateProviderResponse:
        return await manager.validate(
            payload.provider_id,
            api_base=payload.api_base,
            api_key=payload.api_key,
        )
```

- [ ] **Step 2.4: Write the failing route tests**

Append to `tests/plugins/test_providers_plugin.py`:

```python
async def test_validate_route_returns_model_count(api_client, monkeypatch):
    # Stub httpx so the live probe never hits the network.
    import httpx

    class _FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, headers=None):
            return _FakeResponse(
                {"data": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]}
            )

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    response = await api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "lmstudio",
            "apiBase": "http://localhost:1234/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["modelCount"] == 3


async def test_validate_route_handles_offline_provider(api_client, monkeypatch):
    import httpx

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, url, headers=None):
            raise httpx.ConnectError("connection refused")

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    response = await api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "openai",
            "apiBase": "http://127.0.0.1:1/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert "error" in body and body["error"]


async def test_validate_route_unknown_provider(api_client):
    response = await api_client.post(
        "/api/providers/validate",
        json={
            "providerId": "bogus",
            "apiBase": "http://localhost:1234/v1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is False
    assert body["error"] == "unknown provider"
```

- [ ] **Step 2.5: Run the new tests**

Run: `uv run pytest tests/plugins/test_providers_plugin.py -v`
Expected: 5 total tests PASS (2 from Task 1 + 3 from Task 2).

- [ ] **Step 2.6: Run the backend fast gate**

Run:
```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```
Expected: PASS.

- [ ] **Step 2.7: Commit**

```bash
git add src/omniscribe/plugins/providers.py tests/plugins/test_providers_plugin.py
git commit -m "feat(providers): add POST /api/providers/validate route"
```

---

## Phase 2 — Flutter: Auth Banner Plumbing

### Task 3: Add `authRequiredProvider` + wire 401 detection in `ApiClient`

**Files:**
- Modify: `client/lib/data/providers/repository_providers.dart`
- Modify: `client/lib/core/network/api_client.dart`

- [ ] **Step 3.1: Read the current `ApiClient` to find every method that wraps Dio**

Read `client/lib/core/network/api_client.dart`. Identify the `get`, `post`, `postMultipart`, `postMultipartBytes`, `getBytes` methods and the exception-handling block at the bottom of each. The 401 detection has to hook into the `on DioException` block that already rethrows as `UnauthorizedException` (or wherever `e.response?.statusCode == 401` is currently checked).

- [ ] **Step 3.2: Add the `onUnauthorized` field + constructor param to `ApiClient`**

In the `ApiClient` class (top of the file, after the existing constructor args), add:

```dart
  final void Function()? onUnauthorized;
```

In the `ApiClient` constructor body (inside the `:` initializer list or as a named arg), add `this.onUnauthorized`. Adjust to match the existing constructor shape — if `ApiClient` uses a single positional `this._baseUrl` plus named optionals, the new field becomes `this.onUnauthorized` in the named block.

- [ ] **Step 3.3: Call `onUnauthorized?.call()` before rethrowing in every method**

In each of `_request`, `_get`, `_post`, `_postMultipart`, `_postMultipartBytes`, `_getBytes` (whichever names the file uses), find the `on DioException catch (e) { ... rethrow; }` block. Add a single line at the top of the catch block:

```dart
      if (e.response?.statusCode == 401) onUnauthorized?.call();
```

If the file already raises `UnauthorizedException` for 401s (the `api_exceptions.dart` definitions suggest yes), hook the callback **before** the throw — the callback is for *flagging the UI*, the exception propagation is unchanged.

- [ ] **Step 3.4: Add `authRequiredProvider` to `repository_providers.dart`**

Append to `client/lib/data/providers/repository_providers.dart`:

```dart
/// True when the API client has observed a 401 since the last dismiss.
/// Mounted as a banner by AppShell; flipping it does not auto-clear.
final authRequiredProvider = StateProvider<bool>((ref) => false);
```

- [ ] **Step 3.5: Wire `onUnauthorized` in the `apiClientProvider` factory**

In `repository_providers.dart`, locate the `apiClientProvider` (search for `apiClientProvider`). Pass `onUnauthorized: () => ref.read(authRequiredProvider.notifier).state = true` into the `ApiClient(...)` constructor call.

- [ ] **Step 3.6: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 3.7: Commit**

```bash
git add client/lib/data/providers/repository_providers.dart client/lib/core/network/api_client.dart
git commit -m "feat(client): flag auth-required on 401 via authRequiredProvider"
```

### Task 4: Create `AuthRequiredBanner` widget

**Files:**
- Create: `client/lib/presentation/common/auth_required_banner.dart`
- Create: `client/test/presentation/auth_required_banner_test.dart`

- [ ] **Step 4.1: Write the failing widget test**

Create `client/test/presentation/auth_required_banner_test.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/presentation/common/auth_required_banner.dart';

void main() {
  testWidgets('hides by default', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: AuthRequiredBanner())),
      ),
    );
    expect(find.text('Authentication required'), findsNothing);
  });

  testWidgets('shows when authRequiredProvider is true', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRequiredProvider.overrideWith((ref) => true),
        ],
        child: const MaterialApp(
          home: Scaffold(body: AuthRequiredBanner()),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Authentication required'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);
  });

  testWidgets('dismiss button clears the flag', (tester) async {
    final container = ProviderContainer(
      overrides: [authRequiredProvider.overrideWith((ref) => true)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: Scaffold(body: AuthRequiredBanner()),
        ),
      ),
    );
    await tester.pump();
    expect(container.read(authRequiredProvider), isTrue);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();
    expect(container.read(authRequiredProvider), isFalse);
  });
}
```

- [ ] **Step 4.2: Run the test to verify it fails**

Run: `cd client && flutter test test/presentation/auth_required_banner_test.dart`
Expected: FAIL — `auth_required_banner.dart` does not exist.

- [ ] **Step 4.3: Create the widget**

Create `client/lib/presentation/common/auth_required_banner.dart`:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';

/// Dismissible banner shown when the API client has observed a 401 response
/// since the last dismiss. Matches the Svelte `AuthRequiredBanner.svelte`
/// reference; the current server does not enforce auth (deferred per harness
/// rebuild spec), so this banner is a no-op until the auth middleware ships.
class AuthRequiredBanner extends ConsumerWidget {
  const AuthRequiredBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final visible = ref.watch(authRequiredProvider);
    if (!visible) return const SizedBox.shrink();

    final colors = context.colors;
    void openSettings() {
      ref.read(authRequiredProvider.notifier).state = false;
    }

    void dismiss() {
      ref.read(authRequiredProvider.notifier).state = false;
    }

    return Semantics(
          container: true,
          liveRegion: true,
          label: 'Authentication required',
          child: Container(
        margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      decoration: BoxDecoration(
        color: colors.danger.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(6),
        border: Border(
          left: BorderSide(color: colors.danger, width: 4),
          top: BorderSide(color: colors.danger.withValues(alpha: 0.30)),
          right: BorderSide(color: colors.danger.withValues(alpha: 0.30)),
          bottom: BorderSide(color: colors.danger.withValues(alpha: 0.30)),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded,
              size: 16, color: colors.danger, semanticLabel: 'Warning'),
          const SizedBox(width: 8),
          Expanded(
            child: Text.rich(
              TextSpan(
                children: [
                  TextSpan(
                    text: 'Authentication required',
                    style: TextStyle(
                      color: colors.textPrimary,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  TextSpan(
                    text:
                        ' — the API rejected the request with a 401. Set a bearer token in Settings to continue.',
                    style: TextStyle(color: colors.textMuted),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(width: 8),
          AppButton(
            text: 'Open Settings',
            variant: AppButtonVariant.primary,
            size: AppButtonSize.sm,
            onPressed: openSettings,
          ),
          const SizedBox(width: 4),
          IconButton(
            tooltip: 'Dismiss authentication banner',
            onPressed: dismiss,
            icon: const Icon(Icons.close, size: 14),
          ),
        ],
        ),
      ),
    );
  }
}
```

If `AppColorScheme.danger` does not exist, use the closest available token from `app_colors.dart` (typically `colors.error`); if `AppButtonVariant.primary` / `AppButtonSize.sm` differ, mirror the surrounding widget style.

- [ ] **Step 4.4: Run the tests to verify they pass**

Run: `cd client && flutter test test/presentation/auth_required_banner_test.dart`
Expected: 3 tests PASS.

- [ ] **Step 4.5: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 4.6: Commit**

```bash
git add client/lib/presentation/common/auth_required_banner.dart client/test/presentation/auth_required_banner_test.dart
git commit -m "feat(client): add AuthRequiredBanner widget for 401 parity"
```

### Task 5: Mount `AuthRequiredBanner` in `AppShell`

**Files:**
- Modify: `client/lib/presentation/shell/app_shell.dart`

- [ ] **Step 5.1: Write the failing widget test**

Append to `client/test/presentation/app_shell_test.dart` (read the file first to match its existing style):

```dart
testWidgets('renders AuthRequiredBanner when flag is true', (tester) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authRequiredProvider.overrideWith((ref) => true),
      ],
      child: const MaterialApp(home: AppShell()),
    ),
  );
  await tester.pump();
  expect(find.text('Authentication required'), findsOneWidget);
});
```

Add `import 'package:omniscribe_client/data/providers/repository_providers.dart';` to the imports.

- [ ] **Step 5.2: Run the test to verify it fails**

Run: `cd client && flutter test test/presentation/app_shell_test.dart`
Expected: FAIL — banner is not mounted.

- [ ] **Step 5.3: Mount the banner above `TabRibbon`**

In `client/lib/presentation/shell/app_shell.dart`, add the import:

```dart
import 'package:omniscribe_client/presentation/common/auth_required_banner.dart';
```

Wrap the `body:` `Column` so the banner is the first child:

```dart
          body: SafeArea(
            child: Column(
              children: [
                const AuthRequiredBanner(),
                const TabRibbon(),
                Expanded(child: currentScreen),
              ],
            ),
          ),
```

- [ ] **Step 5.4: Run the test to verify it passes**

Run: `cd client && flutter test test/presentation/app_shell_test.dart`
Expected: PASS.

- [ ] **Step 5.5: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 5.6: Commit**

```bash
git add client/lib/presentation/shell/app_shell.dart client/test/presentation/app_shell_test.dart
git commit -m "feat(client): mount AuthRequiredBanner in AppShell"
```

---

## Phase 3 — Flutter: Model Discovery Rewiring

### Task 6: Split `ConfigRepository.getModels`

**Files:**
- Modify: `client/lib/data/repositories/config_repository.dart`
- Test: `client/test/data/config_repository_test.dart` (extend)

- [ ] **Step 6.1: Read the current `ConfigRepository` and its test file**

Read `client/lib/data/repositories/config_repository.dart` and the existing test. Confirm the `ApiClient.get` signature returns `Map<String, dynamic>`.

- [ ] **Step 6.2: Write the failing tests**

Append to `client/test/data/config_repository_test.dart`:

```dart
test('getModelsForProvider parses models list', () async {
  final client = _MockApiClient(response: {'models': ['a', 'b', 'c']});
  final repo = ConfigRepositoryImpl(client);
  final models = await repo.getModelsForProvider('lmstudio');
  expect(models, ['a', 'b', 'c']);
  expect(client.lastPath, '/api/providers/lmstudio/models');
});

test('getModelsForProvider returns empty list on unexpected shape', () async {
  final client = _MockApiClient(response: {'unexpected': true});
  final repo = ConfigRepositoryImpl(client);
  final models = await repo.getModelsForProvider('lmstudio');
  expect(models, isEmpty);
});

test('getModels namespace mapping', () async {
  final client = _MockApiClient(response: {'models': ['m1']});
  final repo = ConfigRepositoryImpl(client);
  expect(await repo.getModels(namespace: 'general'), ['m1']);
  expect(await repo.getModels(namespace: 'translation'), isEmpty);
  expect(await repo.getModels(namespace: 'transcription'), isEmpty);
});
```

Define `_MockApiClient` at the top of the file (it likely already exists in a different shape; if so, adapt the calls to use the existing mock and just assert on the `lastPath`/`response` fields).

- [ ] **Step 6.3: Run the test to verify it fails**

Run: `cd client && flutter test test/data/config_repository_test.dart`
Expected: FAIL — `getModelsForProvider` does not exist.

- [ ] **Step 6.4: Implement `getModelsForProvider` and reshape `getModels`**

Replace the body of `ConfigRepositoryImpl` (just the `getModels` method and the new method):

```dart
  @override
  Future<List<String>> getModelsForProvider(String providerId) async {
    final json = await _apiClient.get<Map<String, dynamic>>(
      '/api/providers/$providerId/models',
    );
    final list = <String>[];
    if (json['models'] is List) {
      for (final item in json['models'] as List) {
        if (item != null) list.add(item.toString());
      }
    }
    return list;
  }

  @override
  Future<List<String>> getModels({String namespace = 'general'}) async {
    switch (namespace) {
      case 'translation':
      case 'transcription':
        // Deferred per harness rebuild spec.
        return const <String>[];
      case 'general':
      case 'ocr':
      default:
        // Phase A: hardcode 'lmstudio' as the default OCR/general provider
        // until the SettingsNotifier-driven override is wired.
        return getModelsForProvider('lmstudio');
    }
  }
```

Add `getModelsForProvider(String providerId)` to the `ConfigRepository` abstract class signature as well.

- [ ] **Step 6.5: Run the test to verify it passes**

Run: `cd client && flutter test test/data/config_repository_test.dart`
Expected: PASS.

- [ ] **Step 6.6: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 6.7: Commit**

```bash
git add client/lib/data/repositories/config_repository.dart client/test/data/config_repository_test.dart
git commit -m "feat(client): split ConfigRepository.getModels into provider-based discovery"
```

### Task 7: Update `SettingsNotifier.load()` to use the new repo method

**Files:**
- Modify: `client/lib/data/providers/settings_notifier.dart`
- Test: `client/test/data/settings_notifier_test.dart` (extend)

- [ ] **Step 7.1: Read `SettingsNotifier.load()` to confirm the call shape**

The existing `load()` calls `await _repo.getModels(namespace: 'ocr')` etc. Confirm `state.activeProviderId` is set BEFORE the model calls (it is — from `state.copyWith(activeProviderId: config.ocrProvider ?? state.activeProviderId, ...)`).

- [ ] **Step 7.2: Write the failing test**

Append to `client/test/data/settings_notifier_test.dart`:

```dart
test('load() routes ocr models through active provider', () async {
  // Stub repo: getModelsForProvider('openai') → ['gpt-4o']
  // Assert SettingsState.ocrModels == ['gpt-4o'].
});
```

(Adapt the stub/mock to whatever pattern the file already uses. The exact assertion text doesn't matter — what matters is that `ocrModels` ends up populated via the active provider, and translation/transcription are empty.)

- [ ] **Step 7.3: Run the test to verify it fails**

Run: `cd client && flutter test test/data/settings_notifier_test.dart`
Expected: FAIL — current implementation calls the deprecated `/api/models/ocr` path.

- [ ] **Step 7.4: Rewrite the `load()` body**

In `client/lib/data/providers/settings_notifier.dart`, replace the three `getModels` calls inside `load()` with:

```dart
      final ocrModels = await _repo.getModelsForProvider(state.activeProviderId);
      // Translation and transcription routes are deferred per the harness
      // rebuild spec; we deliberately do not call the server for them.
      final translationModels = <String>[];
      final transcriptionModels = <String>[];
```

- [ ] **Step 7.5: Run the test to verify it passes**

Run: `cd client && flutter test test/data/settings_notifier_test.dart`
Expected: PASS.

- [ ] **Step 7.6: Commit**

```bash
git add client/lib/data/providers/settings_notifier.dart client/test/data/settings_notifier_test.dart
git commit -m "feat(client): settings load() uses active provider for model discovery"
```

---

## Phase 4 — Flutter: Keyboard Shortcut Plumbing

### Task 8: Add `filePickSignal` to `WorkstationState` + signal methods to `WorkstationNotifier`

**Files:**
- Modify: `client/lib/data/providers/workstation_state.dart`
- Modify: `client/lib/data/providers/workstation_notifier.dart`
- Test: `client/test/data/workstation_notifier_test.dart` (extend)

- [ ] **Step 8.1: Read the current `WorkstationState` to find the field cluster**

Confirm `WorkstationState` is an `@immutable` class with a `const WorkstationState.initial()` factory and a `copyWith`. Add a new field with `0` default.

- [ ] **Step 8.2: Add `filePickSignal` field**

In `WorkstationState`:

1. Add `required this.filePickSignal,` to the constructor.
2. In `WorkstationState.initial()`, add `filePickSignal = 0,`.
3. In the field declarations, add `final int filePickSignal;`.
4. In `copyWith`, add `int? filePickSignal,` and pass `filePickSignal ?? this.filePickSignal` into the constructor.
5. Add `filePickSignal` to the `==` and `hashCode` overrides (use `Object.hash`).

- [ ] **Step 8.3: Write the failing test**

Append to `client/test/data/workstation_notifier_test.dart`:

```dart
test('incrementFilePick bumps the signal', () {
  final container = ProviderContainer(/* overrides as the file uses */);
  addTearDown(container.dispose);
  final notifier = container.read(workstationProvider.notifier);
  expect(container.read(workstationProvider).filePickSignal, 0);
  notifier.incrementFilePick();
  expect(container.read(workstationProvider).filePickSignal, 1);
});
```

- [ ] **Step 8.4: Run the test to verify it fails**

Run: `cd client && flutter test test/data/workstation_notifier_test.dart`
Expected: FAIL — `incrementFilePick` does not exist.

- [ ] **Step 8.5: Add `incrementFilePick` and `processCurrentDocument` to `WorkstationNotifier`**

In `client/lib/data/providers/workstation_notifier.dart`:

```dart
  /// Increments the file-pick signal so any mounted listener (the upload
  /// dropzone) opens its native file picker. Idempotent on intent: every
  /// tap fires exactly one picker dialog.
  void incrementFilePick() {
    state = state.copyWith(filePickSignal: state.filePickSignal + 1);
  }

  /// Convenience for the Ctrl+Enter shortcut: process the current document
  /// with default settings (the workstation dock's tweaked values are not
  /// observable from the AppShell key handler in Phase A).
  Future<void> processCurrentDocument() async {
    await processOcrSync(settings: ProcessSettings.defaultSettings());
  }
```

Add `import 'package:omniscribe_client/data/models/process_settings.dart';` if not already present.

- [ ] **Step 8.6: Run the test to verify it passes**

Run: `cd client && flutter test test/data/workstation_notifier_test.dart`
Expected: PASS.

- [ ] **Step 8.7: Commit**

```bash
git add client/lib/data/providers/workstation_state.dart client/lib/data/providers/workstation_notifier.dart client/test/data/workstation_notifier_test.dart
git commit -m "feat(client): add filePickSignal and processCurrentDocument to workstation notifier"
```

### Task 9: Add `ref.listen` in `UploadDropzone` for `filePickSignal`

**Files:**
- Modify: `client/lib/presentation/workstation/controls/upload_dropzone.dart`

- [ ] **Step 9.1: Read `UploadDropzone` to find its private `_pickFile()` method**

Confirm the widget is a `ConsumerStatefulWidget` (or convert it to one if it isn't — this is a Phase A scope adjustment). Identify the existing private `_pickFile()` (or equivalent) method.

- [ ] **Step 9.2: Add the `ref.listen` in `build`**

In the widget's `build` method, before the return statement:

```dart
    ref.listen<int>(
      workstationProvider.select((s) => s.filePickSignal),
      (prev, next) {
        if (prev != null && next > prev) {
          _pickFile();
        }
      },
    );
```

Add the import:

```dart
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
```

(Already imported in most files; check first.)

- [ ] **Step 9.3: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 9.4: Run the existing widget test for the dropzone**

Run: `cd client && flutter test test/presentation/workstation_screen_test.dart`
Expected: PASS (no behavior change for existing tests).

- [ ] **Step 9.5: Commit**

```bash
git add client/lib/presentation/workstation/controls/upload_dropzone.dart
git commit -m "feat(client): dropzone reacts to filePickSignal"
```

### Task 10: Bind `Ctrl+O` and `Ctrl+Enter` shortcuts in `AppShell`

**Files:**
- Modify: `client/lib/presentation/shell/app_shell.dart`
- Test: `client/test/presentation/app_shell_test.dart` (extend)

- [ ] **Step 10.1: Write the failing tests**

Append to `client/test/presentation/app_shell_test.dart`:

```dart
testWidgets('Ctrl+O on workstation triggers file pick signal', (tester) async {
  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(home: AppShell()),
    ),
  );
  await tester.pump();
  // Force workstation tab via the active tab provider.
  // (Adjust the override shape to match the file's existing tests.)
  // Then send Ctrl+O.
  await tester.sendKeyEvent(LogicalKeyboardKey.keyO, control: true);
  await tester.pump();
  final ws = /* read workstationProvider via container */;
  expect(ws.filePickSignal, greaterThan(0));
});

testWidgets('Ctrl+Enter on workstation with document triggers processing',
    (tester) async {
  // Seed workstation state with hasDocument=true.
  // Send Ctrl+Enter.
  // Assert processCurrentDocument() was invoked (e.g., by stubbing
  // OcrRepository.processOcrSync).
});
```

- [ ] **Step 10.2: Run the tests to verify they fail**

Run: `cd client && flutter test test/presentation/app_shell_test.dart`
Expected: FAIL — no shortcut bindings for Ctrl+O / Ctrl+Enter.

- [ ] **Step 10.3: Add the two bindings to `CallbackShortcuts`**

In `app_shell.dart`, locate the `CallbackShortcuts` map. Add two entries (keep the existing `Ctrl+1..7` and `Ctrl+S` entries):

```dart
        const SingleActivator(LogicalKeyboardKey.keyO, control: true): () {
          final activeTab = ref.read(activeTabProvider);
          if (activeTab == AppTab.workstation) {
            ref.read(workstationProvider.notifier).incrementFilePick();
          }
        },
        const SingleActivator(LogicalKeyboardKey.enter, control: true): () {
          final activeTab = ref.read(activeTabProvider);
          final wsState = ref.read(workstationProvider);
          if (activeTab == AppTab.workstation && wsState.hasDocument) {
            // ignore: unawaited_futures
            ref.read(workstationProvider.notifier).processCurrentDocument();
          }
        },
```

- [ ] **Step 10.4: Run the tests to verify they pass**

Run: `cd client && flutter test test/presentation/app_shell_test.dart`
Expected: PASS.

- [ ] **Step 10.5: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 10.6: Commit**

```bash
git add client/lib/presentation/shell/app_shell.dart client/test/presentation/app_shell_test.dart
git commit -m "feat(client): bind Ctrl+O and Ctrl+Enter shortcuts in AppShell"
```

---

## Phase 5 — Flutter: Settings Cleanup + Web Build Verification

### Task 11: Replace "Auth token UI deferred" badge in settings screen

**Files:**
- Modify: `client/lib/presentation/settings/settings_screen.dart`

- [ ] **Step 11.1: Locate the badge text**

Search for `Auth token UI deferred to slice 5` in the file. It is inside `_buildSecurityAuthTab`.

- [ ] **Step 11.2: Replace the badge**

Change:

```dart
                AppBadge(
                  label: 'Auth token UI deferred to slice 5',
                  variant: AppBadgeVariant.neutral,
                ),
```

To:

```dart
                AppBadge(
                  label: 'Auth middleware deferred — settings have no effect today',
                  variant: AppBadgeVariant.neutral,
                ),
```

- [ ] **Step 11.3: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 11.4: Commit**

```bash
git add client/lib/presentation/settings/settings_screen.dart
git commit -m "chore(client): honest badge copy on settings auth tab"
```

### Task 12: Configure and verify Flutter web build

**Files:**
- Create: `client/scripts/build_web.sh`
- Modify (if missing): `client/web/` directory bootstrap

- [ ] **Step 12.1: Verify `client/web/` exists**

Run: `cd client && ls web`
Expected: directory exists with `index.html`, `manifest.json`, `favicon.png`.

If it does not exist:

Run: `cd client && flutter create --platforms=web .`
Expected: `web/` directory is created (additive; does not touch any other platform's source).

- [ ] **Step 12.2: Build the web release**

Run: `cd client && flutter build web --release`
Expected: build succeeds; `client/build/web/index.html` exists.

- [ ] **Step 12.3: Create the helper script**

Create `client/scripts/build_web.sh`:

```bash
#!/usr/bin/env bash
# Build the Flutter web bundle for manual / Phase-B verification.
# Phase A: out of CI; run locally before tagging a release.
set -euo pipefail
cd "$(dirname "$0")/.."
flutter build web --release
echo "Built client/build/web/ — serve with:"
echo "  cd client/build/web && python -m http.server 8080"
```

- [ ] **Step 12.4: Make the script executable**

Run: `git update-index --chmod=+x client/scripts/build_web.sh`
(or equivalent: just commit it; the `git update-index` step normalizes the mode in the index.)

- [ ] **Step 12.5: Commit**

```bash
git add client/web/ client/scripts/build_web.sh
git commit -m "build(client): verify flutter web build target"
```

---

## Phase 6 — Verification Gates

### Task 13: Backend fast gate

**Files:** none (verification only)

- [ ] **Step 13.1: Run the backend fast gate**

Run:

```bash
uv run ruff check src tests
uv run ruff format src tests --check
uv run mypy src
uv run pytest -m "not slow"
```

Expected: PASS, 0 ruff/mypy issues.

### Task 14: Flutter gate

**Files:** none (verification only)

- [ ] **Step 14.1: Run `flutter analyze`**

Run: `cd client && flutter analyze`
Expected: 0 issues.

- [ ] **Step 14.2: Run `flutter test`**

Run: `cd client && flutter test`
Expected: all tests PASS (including the new auth banner, dropzone listen, shortcut, model-discovery, settings load tests).

- [ ] **Step 14.3: Build Windows desktop**

Run: `cd client && flutter build windows --debug`
Expected: build succeeds; `client/build/windows/runner_debug.exe` (or platform equivalent) exists.

- [ ] **Step 14.4: Build web release**

Run: `cd client && flutter build web --release`
Expected: build succeeds; `client/build/web/index.html` exists.

### Task 15: Manual smoke checklist

**Files:** none (verification only)

- [ ] **Step 15.1: Start the backend**

Run: `uv run omniscribe-server --port 8000`
Expected: server boots, `GET /api/health` returns 200.

- [ ] **Step 15.2: Smoke the new routes**

Run:

```bash
curl -X POST http://127.0.0.1:8000/api/providers/active \
  -H 'Content-Type: application/json' \
  -d '{"providerId":"lmstudio","apiBase":"http://localhost:1234/v1","apiKey":"","model":"allenai/olmocr-2-7b"}'
```

Expected: `{"status":"ok","providerId":"lmstudio","apiBase":"http://localhost:1234/v1","model":"allenai/olmocr-2-7b"}` (200).

Run:

```bash
curl -X POST http://127.0.0.1:8000/api/providers/validate \
  -H 'Content-Type: application/json' \
  -d '{"providerId":"bogus","apiBase":"http://localhost:1234/v1"}'
```

Expected: `{"valid":false,"modelCount":0,"error":"unknown provider"}` (200).

- [ ] **Step 15.3: Run the Flutter web bundle against the server**

Run: `cd client/build/web && python -m http.server 8080`

Then open `http://127.0.0.1:8080/` in a browser. Verify:

- Settings screen loads OCR models (visible in the OCR Pipeline tab if your Phase A keeps the legacy input field).
- Provider modal "Validate" surfaces the result.
- Provider modal "Set active" updates the server.
- Workstation: `Ctrl+O` opens the file picker; `Ctrl+Enter` starts OCR.
- `AuthRequiredBanner` does not appear (no auth middleware on server).

- [ ] **Step 15.4: Mark the plan complete**

All 10 acceptance criteria from the design spec (`docs/superpowers/specs/2026-08-27-flutter-takeover-phase-a-design.md` §"Acceptance criteria") must be checked off.

### Task 16: Ledger sync

**Files:**
- Modify: `docs/superpowers/plans/2026-08-27-flutter-architecture-unification-and-parity.md` (link the Phase A plan in the references section)
- Modify: `ARCHITECTURE.md` (note Phase A under "Pipeline / API surface" if applicable)

- [ ] **Step 16.1: Add a one-line link to this plan in the 2026-08-27 unification plan's references**

Append at the bottom of `docs/superpowers/plans/2026-08-27-flutter-architecture-unification-and-parity.md`:

```markdown
_Follow-up: [2026-08-27-flutter-takeover-phase-a](../plans/2026-08-27-flutter-takeover-phase-a.md) closes the remaining Flutter↔backend wiring (provider-config routes, auth banner, shortcuts, web build) ahead of Phase B Svelte deletion._
```

- [ ] **Step 16.2: Update `ARCHITECTURE.md`**

In [ARCHITECTURE.md](file:///d:/OmniScribe/ARCHITECTURE.md), find the "API surface" or "Pipeline" section. Add a one-paragraph note:

```markdown
### Flutter Takeover (2026-08-27)

The Flutter client is the canonical UI surface; the Svelte reference UI is on
a deprecation path (Phase B = deletion). Provider-config routes
(`/api/providers/active`, `/api/providers/validate`) were added in Phase A;
the deferred translation/transcription/extraction/export/glossary endpoints
remain unimplemented (mock fallback notifiers only).
```

- [ ] **Step 16.3: Commit**

```bash
git add docs/superpowers/plans/2026-08-27-flutter-architecture-unification-and-parity.md ARCHITECTURE.md
git commit -m "docs: cross-link Phase A takeover plan from unification + architecture"
```