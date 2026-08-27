# Flutter Client Consolidation — Foundation + Slice 1 (Settings) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up Flutter Desktop on Windows, fix the cross-folder import lint, and migrate the **Settings** screen to a Riverpod `Notifier<SettingsState>` pattern that wraps `data/repositories/config_repository.dart`. This is slice 1 of the 6-slice consolidation plan in [spec](../specs/2026-08-24-flutter-client-consolidation-design.md).

**Architecture:** Three layers in the consolidated `client/lib/`:

- `core/` — cross-cutting infrastructure (Dio `ApiClient`, `WsClient`, exception hierarchy, endpoint constants, enums).
- `data/` — domain layer (typed `*Repository` interfaces + Riverpod providers/notifiers).
- `presentation/` — UI only (`ConsumerWidget`s that watch Riverpod providers).

Each slice owns one primary `NotifierProvider`. Repositories expose async methods; notifiers wrap them; widgets never call repositories directly. No more `ChangeNotifier` + `InheritedNotifier`.

**Tech Stack:** Flutter 3.24+ (pubspec floor `>=3.19.0`, install latest stable), Dart 3.3+ (floor `<4.0.0`), `flutter_riverpod ^2.5.1` (`Notifier`/`NotifierProvider` 2.x API), `dio ^5.4.3+1`, `mocktail` (added in Task 0.3), `flutter_test` (already in dev_deps), `flutter_lints ^4.0.0`.

---

## File Structure

### Files to create

| Path | Purpose |
|------|---------|
| `client/lib/data/providers/settings_state.dart` | Immutable `SettingsState` with `copyWith` + equality |
| `client/lib/data/providers/settings_notifier.dart` | `SettingsNotifier extends Notifier<SettingsState>` + `settingsStateProvider` |
| `client/test/data/settings_notifier_test.dart` | Notifier unit tests via `ProviderContainer` + `mocktail` |
| `client/windows/` (generated) | Flutter Windows desktop shell (via `flutter create --platforms=windows`) |
| `client/linux/` (generated) | Flutter Linux desktop shell |
| `client/macos/` (generated) | Flutter macOS desktop shell |

### Files to modify

| Path | Change |
|------|--------|
| `client/pubspec.yaml` | Add `mocktail` to `dev_dependencies` |
| `client/lib/presentation/settings/settings_screen.dart` | Rewrite as `ConsumerWidget` watching `settingsStateProvider` |
| `client/lib/presentation/shell/app_shell.dart` | No structural change — it already imports `settings/settings_screen.dart`. Verify after Task 4.1. |
| `client/lib/data/providers/repository_providers.dart` | No structural change — `configRepositoryProvider` already exists; we'll add a seam (overridden `apiBaseUrlProvider`) for tests |
| `client/lib/core/network/api_client.dart` | No structural change — already has `setAuthToken` and `baseUrl` setter. Verify after Task 1.4. |
| `client/.gitignore` | Add `/windows/`, `/linux/`, `/macos/` (auto-generated; keep them untracked for now per the `docs/` convention) |

### Files to delete (after slice 1 lands AND zero importers)

| Path | Replaced by |
|------|-------------|
| `client/lib/state/config_provider.dart` | `data/providers/settings_notifier.dart` |
| `client/lib/state/config_state.dart` | `data/providers/settings_state.dart` |
| `client/lib/services/api_client.dart` | `core/network/api_client.dart` |
| `client/lib/models/config.dart` | `data/models/process_settings.dart` (RuntimeConfig + ConfigUpdate already live there) |

### Future plan references (NOT in this plan)

- Slice 2 — Provider Browser migration. Future plan.
- Slice 3 — Job History + WebSocket migration. Future plan.
- Slice 4 — Translation / Transcription / Glossary / Extraction. Future plan.
- Slice 5 — Workstation (OcrRepository). Future plan.
- Slice 6 — Final cleanup (`state/`, `models/`, `repositories/`, `services/`, `core/theme/`, `presentation/common/`, `presentation/views/`). Future plan.
- Tier A — `path_provider`, file picker, drag-drop, `shared_preferences`. Future plan.

---

## Task 0: Pre-work — Flutter SDK + desktop platform enable

### Task 0.1: Install Flutter SDK on Windows

**Files:** none (host-level install)

- [ ] **Step 1: Install Flutter SDK**

The Flutter SDK is **not currently installed** on this machine. Use `winget` (the simplest path on Windows 10/11):

```powershell
winget install --id Google.Flutter -e --source winget
```

If `winget` is unavailable or fails, fall back to the manual install:

1. Download the latest stable Flutter SDK zip from <https://docs.flutter.dev/get-started/install/windows>.
2. Extract to `C:\src\flutter` (avoid `C:\Program Files\` — it requires admin and breaks some Flutter tooling).
3. Add `C:\src\flutter\bin` to user `PATH`.
4. Log out and back in (so PATH propagates to new shells).

- [ ] **Step 2: Verify `flutter doctor`**

Run in a fresh PowerShell window:

```bash
flutter doctor -v
```

Expected: every line either reports `[OK]` or shows a clear next step. The Windows desktop entry must report `[OK]` for the rest of this plan to work. If it shows `[X] Visual Studio not installed` or `[X] Windows Version (the version of Windows installed)` or `[X] Visual Studio is missing necessary components`, install Visual Studio 2022 with the "Desktop development with C++" workload (required for `flutter build windows`). Note: this is a ~5 GB install; skip if disk-constrained and stop here, raise it to the user.

- [ ] **Step 3: Verify `dart --version`**

```bash
dart --version
```

Expected: `Dart SDK version: 3.x.x` (3.3 or later to match the pubspec floor `<4.0.0`). If it shows Dart 2.x, the Flutter install didn't take effect; re-check PATH.

- [ ] **Step 4: Verify the OmniScribe backend still boots**

```bash
cd d:\OmniScribe
uv run omniscribe-server --port 8000
```

Expected: `Uvicorn running on http://0.0.0.0:8000`. Hit `http://localhost:8000/api/health` in a browser or with `curl`. Expected JSON `{"status":"ok"}` or similar. If this fails, fix backend first before continuing. Ctrl+C to stop.

### Task 0.2: Enable desktop platforms in `client/`

**Files:** `client/.gitignore`, generated `client/windows/`, `client/linux/`, `client/macos/`

- [ ] **Step 1: Run `flutter pub get`**

```bash
cd d:\OmniScribe\client
flutter pub get
```

Expected: `Got dependencies!` or similar. If version-solving fails, capture the error and stop — the pubspec floor or `flutter_riverpod ^2.5.1` constraint likely needs adjustment.

- [ ] **Step 2: Run `flutter create --platforms=windows,linux,macos .`**

```bash
cd d:\OmniScribe\client
flutter create --platforms=windows,linux,macos .
```

Expected: creates `windows/`, `linux/`, `macos/` directories. These are generated platform shells; do NOT edit them by hand.

- [ ] **Step 3: Verify the generated `.gitignore` excludes them**

After Step 2, `client/.gitignore` should contain `/windows/`, `/linux/`, `/macos/`. Open `client/.gitignore` and confirm. If any are missing, add them at the bottom:

```gitignore
# Generated desktop platform shells (one operator runs `flutter create --platforms=...` per machine)
/windows/
/linux/
/macos/
```

This matches the project's existing convention (the `docs/` folder is gitignored — see [spec §2 appendix](../../specs/2026-08-24-flutter-client-consolidation-design.md)).

- [ ] **Step 4: Verify `flutter build windows --debug` succeeds**

```bash
cd d:\OmniScribe\client
flutter build windows --debug
```

Expected: `Built build\windows\x64\runner\Debug\runner.exe` (or similar). First build is slow (~5 min) because it downloads Visual Studio build tools caches.

- [ ] **Step 5: Verify `flutter test` baseline passes**

```bash
cd d:\OmniScribe\client
flutter test
```

Expected: all 7 tests in `client/test/` pass. If any fail, capture the failures — they may indicate the existing `client/` directory has stale state.

### Task 0.3: Add `mocktail` to dev_deps

**Files:** `client/pubspec.yaml`

- [ ] **Step 1: Add `mocktail` to dev_dependencies**

Edit `client/pubspec.yaml`. Add `mocktail` after `flutter_lints`:

```yaml
dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  mocktail: ^1.0.4
```

- [ ] **Step 2: Run `flutter pub get`**

```bash
cd d:\OmniScribe\client
flutter pub get
```

Expected: `Got dependencies!` (mocktail added to `.dart_tool/package_config.json`).

---

## Task 1: Sanity checks on `data/` and `core/`

### Task 1.1: Verify `core/network/api_client.dart` exposes the methods we need

**Files:** `client/lib/core/network/api_client.dart` (read-only)

- [ ] **Step 1: Confirm `ApiClient.baseUrl` is mutable**

Open `client/lib/core/network/api_client.dart`. Confirm:

- A `String get baseUrl` getter exists (line ~57).
- A `set baseUrl(String newBaseUrl)` setter exists that mutates `_dio.options.baseUrl` (line ~59–61).
- `ApiClient({String baseUrl = ApiConstants.defaultBaseUrl, ...})` accepts a base URL (line ~28–50).

If any are missing, add them following the existing style (Dio `_dio.options.baseUrl = ...`).

- [ ] **Step 2: Confirm `ApiClient.setAuthToken` exists**

Confirm `void setAuthToken(String? token)` exists (line ~63). If missing, add it:

```dart
void setAuthToken(String? token) {
  _staticAuthToken = token;
}
```

### Task 1.2: Verify `data/repositories/config_repository.dart` is sufficient for Settings

**Files:** `client/lib/data/repositories/config_repository.dart` (read-only)

- [ ] **Step 1: Confirm the three methods exist**

Open `client/lib/data/repositories/config_repository.dart`. Confirm:

- `Future<RuntimeConfig> getConfig()` (line ~7)
- `Future<RuntimeConfig> updateConfig(ConfigUpdate updates)` (line ~10)
- `Future<List<String>> getModels({String namespace = 'general'})` (line ~13)

If any are missing, add them following the pattern in the file. The `ConfigRepositoryImpl` already implements all three.

- [ ] **Step 2: Confirm `data/models/process_settings.dart` has `RuntimeConfig`, `ConfigUpdate`, `ProcessSettings`**

Open `client/lib/data/models/process_settings.dart`. Confirm:

- `class RuntimeConfig` (around line 570)
- `class ConfigUpdate` (around line 357)
- `class ProcessSettings` (around line 90)

If any are missing, do NOT add them — that means Stack A's domain layer is incomplete, and we need to back-fill from `lib/models/config.dart` first (separate task; raise to user).

### Task 1.3: Verify `data/providers/repository_providers.dart` exposes `configRepositoryProvider`

**Files:** `client/lib/data/providers/repository_providers.dart` (read-only)

- [ ] **Step 1: Confirm providers exist**

Open `client/lib/data/providers/repository_providers.dart`. Confirm:

- `final apiBaseUrlProvider = StateProvider<String>((ref) => 'http://127.0.0.1:8000');` (line ~12)
- `final authTokenProvider = StateProvider<String?>((ref) => null);` (line ~15)
- `final apiClientProvider = Provider<ApiClient>(...)` (line ~18)
- `final configRepositoryProvider = Provider<ConfigRepository>(...)` (line ~49)

If any are missing, add them following the existing style.

### Task 1.4: Confirm `core/network/api_client.dart` does NOT have a `setAuthToken(String?)` that conflicts

The `core/network/api_client.dart` already has `setAuthToken(String?)` setting `_staticAuthToken`. We need to also wire the `authTokenProvider` Riverpod provider. Confirm by reading the `_initInterceptors` method (lines ~67–79). The interceptor reads `_staticAuthToken ?? _authTokenProvider?.call()`. The plan will update the SettingsNotifier to call both `apiClient.setAuthToken(...)` AND `ref.read(authTokenProvider.notifier).state = token`.

---

## Task 2: Imports cleanup pass

The `analysis_options.yaml` has `avoid_relative_lib_imports: true`. Every `../../core/...` style import is currently a lint violation. Fix this in the `data/` and `core/` directories (the Settings slice will need to import from these).

### Task 2.1: Rewrite imports in `client/lib/core/`

**Files:** `client/lib/core/**/*.dart`

- [ ] **Step 1: List every file in `client/lib/core/`**

```bash
cd d:\OmniScribe\client
Get-ChildItem -Path lib\core -Recurse -Filter "*.dart" | ForEach-Object { $_.FullName.Substring((Get-Location).Path.Length + 1) }
```

Expected output: all 11 files in `core/constants/`, `core/enums/`, `core/exceptions/`, `core/network/`, `core/websocket/`.

- [ ] **Step 2: Find every `../` or `../../` import in those files**

```bash
cd d:\OmniScribe\client
Select-String -Path "lib\core\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
```

For each match, identify what it's importing and rewrite to a `package:omniscribe_client/...` form. Examples:

- `import '../constants/api_constants.dart';` → `import 'package:omniscribe_client/core/constants/api_constants.dart';`
- `import '../../constants/api_constants.dart';` → same.

- [ ] **Step 3: Verify `dart analyze` is clean for `core/`**

```bash
cd d:\OmniScribe\client
dart analyze lib/core
```

Expected: `No issues found!`. If `avoid_relative_lib_imports` violations remain, fix them.

- [ ] **Step 4: Commit**

Per the project convention, `client/` is currently untracked. The first commit lands the whole `client/` directory. Confirm with the user before committing (see Task 6.1 for the commit decision).

### Task 2.2: Rewrite imports in `client/lib/data/`

**Files:** `client/lib/data/**/*.dart`

- [ ] **Step 1: Find every `../` or `../../` import in `data/` files**

```bash
cd d:\OmniScribe\client
Select-String -Path "lib\data\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
```

For each match, rewrite to `package:omniscribe_client/...` form. Examples:

- `import '../../core/constants/api_constants.dart';` → `import 'package:omniscribe_client/core/constants/api_constants.dart';`
- `import '../../core/network/api_client.dart';` → same.
- `import '../models/process_settings.dart';` → `import 'package:omniscribe_client/data/models/process_settings.dart';`
- `import '../repositories/config_repository.dart';` → `import 'package:omniscribe_client/data/repositories/config_repository.dart';`

- [ ] **Step 2: Verify `dart analyze` is clean for `data/`**

```bash
cd d:\OmniScribe\client
dart analyze lib/data
```

Expected: `No issues found!`.

### Task 2.3: Rewrite imports in `client/lib/theme/`

**Files:** `client/lib/theme/**/*.dart`

- [ ] **Step 1: Find every `../` or `../../` import in `theme/` files**

```bash
cd d:\OmniScribe\client
Select-String -Path "lib\theme\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
```

Only `theme/docuverse_theme.dart` imports from `theme/docuverse_colors.dart` (relative). Rewrite to `package:omniscribe_client/theme/docuverse_colors.dart`.

- [ ] **Step 2: Verify `dart analyze` is clean for `theme/`**

```bash
cd d:\OmniScribe\client
dart analyze lib/theme
```

Expected: `No issues found!`.

---

## Task 3: Create `SettingsState` (TDD)

### Task 3.1: Write the failing test for `SettingsState.initial`

**Files:** `client/test/data/settings_state_test.dart` (new)

- [ ] **Step 1: Create the test file**

Create `client/test/data/settings_state_test.dart` with:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/settings_state.dart';

void main() {
  group('SettingsState.initial', () {
    test('returns sane defaults: not loading, no runtime config, no error', () {
      const state = SettingsState.initial();
      expect(state.isLoading, isFalse);
      expect(state.runtimeConfig, isNull);
      expect(state.error, isNull);
      expect(state.activeProviderId, 'openai');
      expect(state.ocrModels, isEmpty);
      expect(state.translationModels, isEmpty);
      expect(state.transcriptionModels, isEmpty);
      expect(state.serverBaseUrl, 'http://127.0.0.1:8000');
      expect(state.useAsync, isFalse);
      expect(state.isDarkMode, isFalse);
    });
  });

  group('SettingsState.copyWith', () {
    test('preserves untouched fields', () {
      const before = SettingsState.initial();
      final after = before.copyWith(isLoading: true);
      expect(after.isLoading, isTrue);
      expect(after.runtimeConfig, before.runtimeConfig);
      expect(after.error, before.error);
      expect(after.activeProviderId, before.activeProviderId);
    });

    test('clearError: null error is preserved when explicit null passed', () {
      const before = SettingsState.initial();
      final after = before.copyWith(clearError: true);
      expect(after.error, isNull);
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails (compile error)**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_state_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/settings_state.dart'`. This is the failing test we want — it doesn't exist yet.

### Task 3.2: Implement `SettingsState`

**Files:** `client/lib/data/providers/settings_state.dart` (new)

- [ ] **Step 1: Create `settings_state.dart`**

Create `client/lib/data/providers/settings_state.dart`:

```dart
import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';

@immutable
class SettingsState {
  const SettingsState({
    required this.isLoading,
    required this.runtimeConfig,
    required this.activeProviderId,
    required this.ocrModels,
    required this.translationModels,
    required this.transcriptionModels,
    required this.serverBaseUrl,
    required this.useAsync,
    required this.error,
    required this.isDarkMode,
  });

  /// Initial empty state — no config fetched, no errors, default provider.
  const SettingsState.initial()
      : isLoading = false,
        runtimeConfig = null,
        activeProviderId = 'openai',
        ocrModels = const <String>[],
        translationModels = const <String>[],
        transcriptionModels = const <String>[],
        serverBaseUrl = 'http://127.0.0.1:8000',
        useAsync = false,
        error = null,
        isDarkMode = false;

  final bool isLoading;
  final RuntimeConfig? runtimeConfig;
  final String activeProviderId;
  final List<String> ocrModels;
  final List<String> translationModels;
  final List<String> transcriptionModels;
  final String serverBaseUrl;
  final bool useAsync;
  final String? error;
  final bool isDarkMode;

  SettingsState copyWith({
    bool? isLoading,
    RuntimeConfig? runtimeConfig,
    String? activeProviderId,
    List<String>? ocrModels,
    List<String>? translationModels,
    List<String>? transcriptionModels,
    String? serverBaseUrl,
    bool? useAsync,
    String? error,
    bool? isDarkMode,
    bool clearError = false,
    bool clearRuntimeConfig = false,
  }) {
    return SettingsState(
      isLoading: isLoading ?? this.isLoading,
      runtimeConfig:
          clearRuntimeConfig ? null : (runtimeConfig ?? this.runtimeConfig),
      activeProviderId: activeProviderId ?? this.activeProviderId,
      ocrModels: ocrModels ?? this.ocrModels,
      translationModels: translationModels ?? this.translationModels,
      transcriptionModels: transcriptionModels ?? this.transcriptionModels,
      serverBaseUrl: serverBaseUrl ?? this.serverBaseUrl,
      useAsync: useAsync ?? this.useAsync,
      error: clearError ? null : (error ?? this.error),
      isDarkMode: isDarkMode ?? this.isDarkMode,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is SettingsState &&
        other.isLoading == isLoading &&
        other.runtimeConfig == runtimeConfig &&
        other.activeProviderId == activeProviderId &&
        listEquals(other.ocrModels, ocrModels) &&
        listEquals(other.translationModels, translationModels) &&
        listEquals(other.transcriptionModels, transcriptionModels) &&
        other.serverBaseUrl == serverBaseUrl &&
        other.useAsync == useAsync &&
        other.error == error &&
        other.isDarkMode == isDarkMode;
  }

  @override
  int get hashCode => Object.hash(
        isLoading,
        runtimeConfig,
        activeProviderId,
        Object.hashAll(ocrModels),
        Object.hashAll(translationModels),
        Object.hashAll(transcriptionModels),
        serverBaseUrl,
        useAsync,
        error,
        isDarkMode,
      );
}
```

- [ ] **Step 2: Run the test to verify it passes**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_state_test.dart
```

Expected: **PASS** — both groups, all 3 tests green.

- [ ] **Step 3: Run `dart analyze` on the new file**

```bash
cd d:\OmniScribe\client
dart analyze lib/data/providers/settings_state.dart test/data/settings_state_test.dart
```

Expected: `No issues found!`.

---

## Task 4: Create `SettingsNotifier` (TDD)

### Task 4.1: Write the failing test for `SettingsNotifier.load()`

**Files:** `client/test/data/settings_notifier_test.dart` (new)

- [ ] **Step 1: Create the test file with the first failing test**

Create `client/test/data/settings_notifier_test.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';

class _MockConfigRepository extends Mock implements ConfigRepository {}

void main() {
  late _MockConfigRepository repo;

  setUp(() {
    repo = _MockConfigRepository();
  });

  ProviderContainer makeContainer() {
    return ProviderContainer(
      overrides: [
        configRepositoryProvider.overrideWithValue(repo),
      ],
    );
  }

  group('SettingsNotifier.build', () {
    test('returns SettingsState.initial() before any method call', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(settingsStateProvider);
      expect(state.isLoading, isFalse);
      expect(state.runtimeConfig, isNull);
    });
  });

  group('SettingsNotifier.load', () {
    test('fetches config + models and updates state', () async {
      final config = RuntimeConfig(
        apiBase: 'http://example.test/v1',
        apiKey: '',
        model: 'allenai/olmocr-2-7b',
        ocrProvider: 'openai',
      );
      when(() => repo.getConfig()).thenAnswer((_) async => config);
      when(() => repo.getModels(namespace: 'ocr'))
          .thenAnswer((_) async => ['allenai/olmocr-2-7b', 'qwen2-vl']);
      when(() => repo.getModels(namespace: 'translation'))
          .thenAnswer((_) async => ['nllb-200']);
      when(() => repo.getModels(namespace: 'transcription'))
          .thenAnswer((_) async => ['whisper-1']);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      await notifier.load();

      final state = container.read(settingsStateProvider);
      expect(state.isLoading, isFalse);
      expect(state.runtimeConfig, config);
      expect(state.activeProviderId, 'openai');
      expect(state.ocrModels, ['allenai/olmocr-2-7b', 'qwen2-vl']);
      expect(state.translationModels, ['nllb-200']);
      expect(state.transcriptionModels, ['whisper-1']);
      expect(state.error, isNull);
    });

    test('on failure populates error and clears isLoading', () async {
      when(() => repo.getConfig())
          .thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      await notifier.load();

      final state = container.read(settingsStateProvider);
      expect(state.isLoading, isFalse);
      expect(state.runtimeConfig, isNull);
      expect(state.error, contains('boom'));
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails (compile error)**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_notifier_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/settings_notifier.dart'`. This is the failing test we want.

### Task 4.2: Implement `SettingsNotifier` with `build()` + `load()`

**Files:** `client/lib/data/providers/settings_notifier.dart` (new)

- [ ] **Step 1: Create `settings_notifier.dart`**

Create `client/lib/data/providers/settings_notifier.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/providers/settings_state.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';

final settingsStateProvider =
    NotifierProvider<SettingsNotifier, SettingsState>(
  SettingsNotifier.new,
);

class SettingsNotifier extends Notifier<SettingsState> {
  late final ConfigRepository _repo;

  @override
  SettingsState build() {
    _repo = ref.watch(configRepositoryProvider);
    return const SettingsState.initial();
  }

  Future<void> load() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final config = await _repo.getConfig();
      final ocrModels = await _repo.getModels(namespace: 'ocr');
      final translationModels = await _repo.getModels(namespace: 'translation');
      final transcriptionModels =
          await _repo.getModels(namespace: 'transcription');

      state = state.copyWith(
        isLoading: false,
        runtimeConfig: config,
        activeProviderId: config.ocrProvider ?? state.activeProviderId,
        ocrModels: ocrModels,
        translationModels: translationModels,
        transcriptionModels: transcriptionModels,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }
}
```

- [ ] **Step 2: Run the tests to verify they pass**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_notifier_test.dart
```

Expected: **PASS** — both `build` and `load` groups green.

- [ ] **Step 3: Run `dart analyze` on the new file**

```bash
cd d:\OmniScribe\client
dart analyze lib/data/providers/settings_notifier.dart test/data/settings_notifier_test.dart
```

Expected: `No issues found!`.

### Task 4.3: Add tests for `updateOcr` / `setServerBaseUrl` / `toggleDarkMode`

**Files:** `client/test/data/settings_notifier_test.dart` (modify)

- [ ] **Step 1: Add three more tests at the end of the file**

Append to `client/test/data/settings_notifier_test.dart`:

```dart
  group('SettingsNotifier.updateOcr', () {
    test('posts ConfigUpdate via repo and re-fetches config', () async {
      final initial = RuntimeConfig(
        apiBase: 'http://example.test/v1',
        model: 'allenai/olmocr-2-7b',
        ocrProvider: 'openai',
      );
      final updated = initial.copyWith(model: 'qwen2-vl');
      when(() => repo.getConfig())
          .thenAnswer((_) async => initial);
      when(() => repo.updateConfig(any())).thenAnswer((_) async => updated);
      when(() => repo.getModels(namespace: 'ocr'))
          .thenAnswer((_) async => ['allenai/olmocr-2-7b']);
      when(() => repo.getModels(namespace: 'translation'))
          .thenAnswer((_) async => const <String>[]);
      when(() => repo.getModels(namespace: 'transcription'))
          .thenAnswer((_) async => const <String>[]);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      await notifier.load();
      await notifier.updateOcr(
        const ProcessSettings.defaultSettings().copyWith(model: 'qwen2-vl'),
      );

      final captured = verify(() => repo.updateConfig(captureAny()))
          .captured
          .single as ConfigUpdate;
      expect(captured.model, 'qwen2-vl');

      final state = container.read(settingsStateProvider);
      expect(state.runtimeConfig?.model, 'qwen2-vl');
    });
  });

  group('SettingsNotifier.toggleDarkMode', () {
    test('flips isDarkMode without touching repo', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      expect(container.read(settingsStateProvider).isDarkMode, isFalse);
      notifier.toggleDarkMode();
      expect(container.read(settingsStateProvider).isDarkMode, isTrue);
      notifier.toggleDarkMode();
      expect(container.read(settingsStateProvider).isDarkMode, isFalse);
      verifyNever(() => repo.getConfig());
    });
  });

  group('SettingsNotifier.setServerBaseUrl', () {
    test('updates serverBaseUrl state', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      notifier.setServerBaseUrl('http://localhost:9000');
      expect(container.read(settingsStateProvider).serverBaseUrl,
          'http://localhost:9000');
    });
  });

  group('SettingsNotifier.setUseAsync', () {
    test('updates useAsync locally without round-tripping', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(settingsStateProvider.notifier);

      expect(container.read(settingsStateProvider).useAsync, isFalse);
      notifier.setUseAsync(true);
      expect(container.read(settingsStateProvider).useAsync, isTrue);
      verifyNever(() => repo.updateConfig(any()));
    });
  });
```

- [ ] **Step 2: Run the test to verify it fails (compile error on `updateOcr`)**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_notifier_test.dart
```

Expected: **FAIL** with `'SettingsNotifier' doesn't have instance method 'updateOcr'`.

### Task 4.4: Add `updateOcr`, `setServerBaseUrl`, `toggleDarkMode` to `SettingsNotifier`

**Files:** `client/lib/data/providers/settings_notifier.dart` (modify)

- [ ] **Step 1: Add the three methods to `SettingsNotifier`**

Replace the contents of `client/lib/data/providers/settings_notifier.dart` with:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/providers/settings_state.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';

final settingsStateProvider =
    NotifierProvider<SettingsNotifier, SettingsState>(
  SettingsNotifier.new,
);

class SettingsNotifier extends Notifier<SettingsState> {
  late final ConfigRepository _repo;

  @override
  SettingsState build() {
    _repo = ref.watch(configRepositoryProvider);
    return const SettingsState.initial();
  }

  Future<void> load() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final config = await _repo.getConfig();
      final ocrModels = await _repo.getModels(namespace: 'ocr');
      final translationModels = await _repo.getModels(namespace: 'translation');
      final transcriptionModels =
          await _repo.getModels(namespace: 'transcription');

      state = state.copyWith(
        isLoading: false,
        runtimeConfig: config,
        activeProviderId: config.ocrProvider ?? state.activeProviderId,
        ocrModels: ocrModels,
        translationModels: translationModels,
        transcriptionModels: transcriptionModels,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  Future<void> updateOcr(ProcessSettings next) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      await _repo.updateConfig(
        ConfigUpdate(
          apiBase: next.apiBase,
          apiKey: next.apiKey.isNotEmpty ? next.apiKey : null,
          model: next.model,
          pipelineMode: next.pipelineMode,
          denseMode: next.denseMode,
          denseThreshold: next.denseThreshold,
          dpi: next.dpi,
          concurrency: next.concurrency,
          refine: next.refine,
          maxImageDim: next.maxImageDim,
          selfCorrection: next.selfCorrection,
          binarize: next.binarize,
          dualEngine: next.dualEngine,
          spellcheck: next.spellcheck,
          crossPage: next.crossPage,
          preprocessPages: next.preprocessPages,
          orientationDetection: next.orientationDetection,
          deskew: next.deskew,
          denoise: next.denoise,
          normalizeContrast: next.normalizeContrast,
          cropCleanup: next.cropCleanup,
          qualityRouting: next.qualityRouting,
          documentProcessors: next.documentProcessors,
        ),
      );
      await load();
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  void setServerBaseUrl(String url) {
    state = state.copyWith(serverBaseUrl: url);
    // Trigger a config refresh against the new URL.
    load();
  }

  void setActiveProvider(String id) {
    state = state.copyWith(activeProviderId: id);
  }

  void setUseAsync(bool useAsync) {
    // Optimistic local-only update; the server is updated the next time
    // updateOcr/updateTranslation/etc. are called.
    state = state.copyWith(useAsync: useAsync);
  }

  void toggleDarkMode([bool? forceValue]) {
    state = state.copyWith(isDarkMode: forceValue ?? !state.isDarkMode);
  }
}
```

- [ ] **Step 2: Run the tests to verify all pass**

```bash
cd d:\OmniScribe\client
flutter test test/data/settings_notifier_test.dart
```

Expected: **PASS** — every group, every test green.

- [ ] **Step 3: Run `dart analyze` on the modified files**

```bash
cd d:\OmniScribe\client
dart analyze lib/data/providers/settings_notifier.dart test/data/settings_notifier_test.dart
```

Expected: `No issues found!`.

### Task 4.5: Wire `load()` to fire on app boot

**Files:** `client/lib/main.dart`

- [ ] **Step 1: Trigger `load()` from `OmniScribeApp.build`**

Open `client/lib/main.dart`. Replace its contents with:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/presentation/shell/app_shell.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    const ProviderScope(
      child: OmniScribeApp(),
    ),
  );
}

class OmniScribeApp extends ConsumerStatefulWidget {
  const OmniScribeApp({super.key});

  @override
  ConsumerState<OmniScribeApp> createState() => _OmniScribeAppState();
}

class _OmniScribeAppState extends ConsumerState<OmniScribeApp> {
  @override
  void initState() {
    super.initState();
    // Kick off the initial config fetch once the notifier is available.
    Future.microtask(
      () => ref.read(settingsStateProvider.notifier).load(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final configState = ref.watch(settingsStateProvider);

    return MaterialApp(
      title: 'OmniScribe',
      debugShowCheckedModeBanner: false,
      theme: DocuVerseTheme.lightTheme,
      darkTheme: DocuVerseTheme.darkTheme,
      themeMode: configState.isDarkMode ? ThemeMode.dark : ThemeMode.light,
      home: const AppShell(),
    );
  }
}
```

- [ ] **Step 2: Verify `dart analyze` is clean**

```bash
cd d:\OmniScribe\client
dart analyze lib/main.dart
```

Expected: `No issues found!`.

---

## Task 5: Rewrite `presentation/settings/settings_screen.dart` as `ConsumerWidget`

### Task 5.1: Inspect the live `settings_screen.dart` to preserve behavior

**Files:** `client/lib/presentation/settings/settings_screen.dart` (read-only)

- [ ] **Step 1: Read the entire file and identify all `configState.<x>` accesses**

```bash
cd d:\OmniScribe\client
Get-Content lib/presentation/settings/settings_screen.dart | Select-String -Pattern "configState\."
```

Capture every field the existing screen reads from the `ConfigState` class (`lib/state/config_state.dart`). Map each one to a `SettingsState` field:

| Live `ConfigState` field | New `SettingsState` field |
|-------------------------|-----------------------------|
| `activeProviderId` | `activeProviderId` |
| `isConnected` | (defer — wire in a future slice) |
| `isFetching` | `isLoading` |
| `config` (a `RuntimeConfig`) | `runtimeConfig` |
| `error` | `error` |
| `ocrModels`, `translationModels`, `transcriptionModels` | same |
| `serverBaseUrl` | same |
| `useAsync` (via `config.useAsync`) | `useAsync` |
| `isDarkMode` | same |

For each `configState.method(...)` call (e.g., `ref.read(configProvider.notifier).fetchConfig()`), identify the new equivalent (`ref.read(settingsStateProvider.notifier).load()`).

### Task 5.2: Rewrite the screen to watch `settingsStateProvider`

**Files:** `client/lib/presentation/settings/settings_screen.dart` (modify)

- [ ] **Step 1: Replace the top of the file (imports + class declaration)**

This step is a **rename pass**, not a visual redesign: the 768-line body of `settings_screen.dart` is preserved byte-for-byte — only the state source is changed from `ConfigState` / `configProvider` to `SettingsState` / `settingsStateProvider`.

Replace the entire header (everything above the first `class` declaration) of `client/lib/presentation/settings/settings_screen.dart` with:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_state.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsStateProvider);
    final notifier = ref.read(settingsStateProvider.notifier);
    final tokens = context.docuVerse;
    // ... [PRESERVED BODY] — see substitution table below
  }
}
```

After the header rewrite, apply the substitution table to every reference in the preserved body. Read the existing body once to find every match, then perform the substitutions in order:

| Live reference | New reference |
|----------------|---------------|
| `configState.isFetching` | `settings.isLoading` |
| `configState.config` | `settings.runtimeConfig` |
| `configState.error` | `settings.error` |
| `configState.activeProviderId` | `settings.activeProviderId` |
| `configState.isDarkMode` | `settings.isDarkMode` |
| `configState.ocrModels` | `settings.ocrModels` |
| `configState.translationModels` | `settings.translationModels` |
| `configState.transcriptionModels` | `settings.transcriptionModels` |
| `configState.serverBaseUrl` | `settings.serverBaseUrl` |
| `ref.read(configProvider.notifier).fetchConfig()` | `notifier.load()` |
| `ref.read(configProvider.notifier).updateOcrSettings(payload)` | `notifier.updateOcr(settings)` (drop the raw Map payload) |
| `ref.read(configProvider.notifier).toggleDarkMode()` | `notifier.toggleDarkMode()` |
| `ref.read(configProvider.notifier).setServerBaseUrl(url)` | `notifier.setServerBaseUrl(url)` |
| `ref.read(configProvider.notifier).setUseAsync(b)` | `notifier.setUseAsync(b)` |

**Do NOT** change the visual layout (no widget renames, no color swaps, no section reordering). The goal is identical behavior with a different state source.

- [ ] **Step 2: Verify `dart analyze` is clean**

```bash
cd d:\OmniScribe\client
dart analyze lib/presentation/settings/settings_screen.dart
```

Expected: `No issues found!`. If `configState` references remain, fix them.

- [ ] **Step 3: Run all tests**

```bash
cd d:\OmniScribe\client
flutter test
```

Expected: all tests pass (Settings tests + the 7 pre-existing tests).

---

## Task 6: Delete the old Stack B files and commit

### Task 6.1: Confirm zero remaining importers

**Files:** search

- [ ] **Step 1: Confirm no imports of the files we plan to delete**

```bash
cd d:\OmniScribe\client
Select-String -Path "lib\**\*.dart" -Pattern "state/config_provider|state/config_state|services/api_client|models/config\.dart" -SimpleMatch:$false
```

Expected: **no matches** in `lib/`. If any remain, fix them (likely a few leftover files in `presentation/views/` or `presentation/common/`).

- [ ] **Step 2: Confirm no test imports either**

```bash
cd d:\OmniScribe\client
Select-String -Path "test\**\*.dart" -Pattern "state/config_provider|state/config_state|services/api_client|models/config\.dart" -SimpleMatch:$false
```

Expected: **no matches**.

### Task 6.2: Delete the four files

**Files:** delete

- [ ] **Step 1: Delete `state/config_provider.dart`, `state/config_state.dart`, `services/api_client.dart`, `models/config.dart`**

```bash
cd d:\OmniScribe\client
Remove-Item lib/state/config_provider.dart
Remove-Item lib/state/config_state.dart
Remove-Item lib/services/api_client.dart
Remove-Item lib/models/config.dart
```

- [ ] **Step 2: Run `dart analyze` to confirm nothing breaks**

```bash
cd d:\OmniScribe\client
dart analyze
```

Expected: `No issues found!`.

- [ ] **Step 3: Run all tests**

```bash
cd d:\OmniScribe\client
flutter test
```

Expected: all tests pass.

### Task 6.3: Manual smoke test against the live backend

**Files:** none

- [ ] **Step 1: Boot the backend**

```bash
cd d:\OmniScribe
uv run omniscribe-server --port 8000
```

Leave it running in a separate shell.

- [ ] **Step 2: Launch the Flutter app**

```bash
cd d:\OmniScribe\client
flutter run -d windows
```

Expected: app boots, the `AppShell` shows the top tab ribbon. The Settings tab loads (it was previously the 7th tab; tab order may shift in the future).

- [ ] **Step 3: Navigate to Settings and verify**

Click the Settings tab. Expected:

- The runtime config (model, OCR provider, etc.) is populated from `GET /api/config`.
- The model dropdowns (OCR / translation / transcription) are populated.
- Toggling dark mode flips the theme without hitting the backend.
- If you change a value and save, the backend `POST /api/config` is hit (check the uvicorn logs).

- [ ] **Step 4: Shut down**

Stop the Flutter app (close the window). Ctrl+C the backend.

### Task 6.4: Commit

**Files:** all changes since `client/` was untracked.

> **Note:** Per the project convention (`.gitignore` excludes `docs/`, `frontend/`/changes are separate commits, etc.), the user should confirm the exact commit shape. The recommended commit is **one** commit landing the entire slice at once, on a new branch like `feat/client-consolidation-slice1`.

- [ ] **Step 1: Confirm the commit boundary with the user**

Tell the user: "Slice 1 is ready to commit. Suggested branch: `feat/client-consolidation-slice1`. Suggested message: `feat(client): settings slice — Riverpod NotifierProvider replaces state/config_provider`."

Get explicit confirmation before running `git add` / `git commit`.

- [ ] **Step 2: Stage and commit**

Only after the user confirms:

```bash
cd d:\OmniScribe
git checkout -b feat/client-consolidation-slice1
git add client/
git commit -m "feat(client): settings slice — Riverpod NotifierProvider replaces state/config_provider"
```

---

## Self-Review (run before claiming done)

After completing all tasks, walk through this checklist:

- [ ] **`dart analyze` exits 0** across the entire `client/` tree:

  ```bash
  cd d:\OmniScribe\client
  dart analyze
  ```

- [ ] **`flutter test` exits 0** (all old + new tests pass):

  ```bash
  cd d:\OmniScribe\client
  flutter test
  ```

- [ ] **`flutter build windows --debug` succeeds**:

  ```bash
  cd d:\OmniScribe\client
  flutter build windows --debug
  ```

- [ ] **Zero relative imports remain** in `client/lib/`:

  ```bash
  cd d:\OmniScribe\client
  Select-String -Path "lib\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
  ```

  Expected: no matches.

- [ ] **Manual smoke test passed** against the live backend (Task 6.3).

- [ ] **No `// ignore:` lines were added** in any new file (search: `Select-String -Path "lib\data\providers\settings_*" -Pattern "ignore:"`).

- [ ] **No commit was made without user confirmation** (Task 6.4 step 1).

---

## Reference

- **Spec:** [2026-08-24-flutter-client-consolidation-design.md](../../specs/2026-08-24-flutter-client-consolidation-design.md) — the design this plan implements slice 1 of.
- **Slices 2–6:** outlined in [spec §3.2](../../specs/2026-08-24-flutter-client-consolidation-design.md#slice-ordering); each gets its own plan.
- **Phase 2 roadmap:** Tiers A–E in [spec §5](../../specs/2026-08-24-flutter-client-consolidation-design.md#5-post-consolidation-feature-roadmap-phase-2--out-of-scope-for-this-design); deferred until slice 6 lands.