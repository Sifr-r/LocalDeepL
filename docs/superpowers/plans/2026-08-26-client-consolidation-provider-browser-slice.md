# Provider Browser Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the **Provider Browser** feature from Stack A (`state/provider_browser_*`, `repositories/providers_repository`, `models/provider`) to Stack B (`data/providers/provider_notifier`, `data/repositories/provider_repository`, `data/models/provider_preset`), making `data/providers/providerBrowserProvider` the single source of truth and deleting the legacy files. This is slice 3 of the 6-slice consolidation plan in [spec](../specs/2026-08-24-flutter-client-consolidation-design.md) (the user executed the Jobs slice ahead of this one in the original sequence).

**Architecture:** Two-layer domain surface in `client/lib/data/`:
- `data/providers/provider_browser_state.dart` — immutable `ProviderBrowserState` (`copyWith` + `clearError` + `clearActiveProvider` + derived `filteredProviders` / `popularProviders` / `otherProviders` getters).
- `data/providers/provider_notifier.dart` — `ProviderBrowserNotifier extends Notifier<ProviderBrowserState>` exposing `fetchProviders`, `fetchModelsForProvider(id)`, `validateProvider(id, base, key, model)`, `setActiveProvider(id, base, key, model)`, `setSearchQuery(q)`, `selectActiveProvider(p)`. Wires the existing `settingsStateProvider.setActiveProvider(id)` + `settingsStateProvider.load()` on `setActiveProvider` (cross-notifier coordination, matches legacy behaviour).

Reuses `data/repositories/provider_repository.dart` (already implements `ProviderRepository` against `ApiClient`) and `data/models/provider_preset.dart` (already has the immutable `ProviderPreset` + `ValidateProviderRequest/Response` + `SetActiveProviderRequest/Response` + `ProviderModelsResponse`).

**Tech Stack:** Flutter 3.24+ (pubspec floor `>=3.19.0`, install latest stable), Dart 3.3+ (floor `<4.0.0`), `flutter_riverpod ^2.5.1` (`Notifier` / `NotifierProvider` 2.x API), `mocktail` (already in dev_deps since slice 1), `flutter_test` (already in dev_deps).

---

## File Structure

### Files to create

| Path | Purpose |
|------|---------|
| `client/lib/data/providers/provider_browser_state.dart` | Immutable `ProviderBrowserState` with `copyWith` + `clearError` + `clearActiveProvider` + derived getters |
| `client/lib/data/providers/provider_notifier.dart` | `ProviderBrowserNotifier extends Notifier<ProviderBrowserState>` + `providerBrowserProvider` |
| `client/test/data/provider_browser_state_test.dart` | State unit tests (4 cases) |
| `client/test/data/provider_notifier_test.dart` | Notifier unit tests via `ProviderContainer` + `mocktail` (8 cases) |

### Files to modify

| Path | Change |
|------|--------|
| `client/lib/presentation/providers/provider_card.dart` | Replace `package:omniscribe_client/models/provider.dart` with `package:omniscribe_client/data/models/provider_preset.dart`. Field accesses stay identical because `ProviderPreset.constructor` + field names were preserved across the rename. |
| `client/lib/presentation/providers/provider_modal.dart` | Replace `package:omniscribe_client/state/provider_browser_provider.dart` + `package:omniscribe_client/state/provider_browser_state.dart` + `package:omniscribe_client/models/provider.dart` + `package:omniscribe_client/services/api_client.dart` with `package:omniscribe_client/data/providers/provider_notifier.dart` + `package:omniscribe_client/data/models/provider_preset.dart`. All `providerBrowserProvider` references resolve to the new NotifierProvider export of the same name. |
| `client/lib/presentation/settings/settings_screen.dart` | Same import substitution as `provider_modal.dart`. The `ref.watch(providerBrowserProvider)` + `ProviderModal.show(context)` call sites stay identical. |

### Files to delete (after slice lands AND zero importers)

| Path | Replaced by |
|------|-------------|
| `client/lib/state/provider_browser_provider.dart` | `data/providers/provider_notifier.dart` |
| `client/lib/state/provider_browser_state.dart` | `data/providers/provider_browser_state.dart` |
| `client/lib/repositories/providers_repository.dart` | `data/repositories/provider_repository.dart` (already shipped) |
| `client/lib/models/provider.dart` | `data/models/provider_preset.dart` (already shipped) |

`client/lib/services/api_client.dart` is **NOT** deleted in this slice — `state/features_provider.dart` and `repositories/features_repository.dart` still depend on it. Cleanup happens in slice 4 (Features).

---

## Task 1: Create `ProviderBrowserState` (TDD)

**Files:**
- Create: `client/lib/data/providers/provider_browser_state.dart`
- Test: `client/test/data/provider_browser_state_test.dart`

- [ ] **Step 1: Write the failing test file**

Create `client/test/data/provider_browser_state_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';

void main() {
  const presetA = ProviderPreset(
    id: 'openai',
    name: 'OpenAI',
    category: 'popular',
    description: 'GPT models',
    recommendedBaseUrl: 'https://api.openai.com/v1',
    defaultModel: 'gpt-4o',
  );
  const presetB = ProviderPreset(
    id: 'ollama',
    name: 'Ollama',
    category: 'local',
    description: 'Local models',
    recommendedBaseUrl: 'http://localhost:11434/v1',
    defaultModel: 'llama3',
  );

  group('ProviderBrowserState.initial', () {
    test('returns sane defaults', () {
      const state = ProviderBrowserState.initial();
      expect(state.providers, isEmpty);
      expect(state.activeProvider, isNull);
      expect(state.validationStatus, isEmpty);
      expect(state.modelsMap, isEmpty);
      expect(state.loadingModelIds, isEmpty);
      expect(state.isFetching, isFalse);
      expect(state.isValidating, isFalse);
      expect(state.searchQuery, isEmpty);
      expect(state.error, isNull);
    });
  });

  group('ProviderBrowserState.copyWith', () {
    test('preserves untouched fields', () {
      const before = ProviderBrowserState.initial();
      final after = before.copyWith(isFetching: true);
      expect(after.isFetching, isTrue);
      expect(after.providers, before.providers);
      expect(after.error, before.error);
      expect(after.searchQuery, before.searchQuery);
    });

    test('clearError: null error is preserved when explicit null passed', () {
      const before = ProviderBrowserState.initial();
      final after = before.copyWith(clearError: true);
      expect(after.error, isNull);
    });

    test('clearActiveProvider forces activeProvider to null', () {
      final before = ProviderBrowserState.initial().copyWith(activeProvider: presetA);
      final after = before.copyWith(clearActiveProvider: true);
      expect(after.activeProvider, isNull);
    });
  });

  group('ProviderBrowserState.filteredProviders', () {
    test('returns all providers when search query is empty', () {
      final state = ProviderBrowserState.initial().copyWith(providers: [presetA, presetB]);
      expect(state.filteredProviders, hasLength(2));
    });

    test('matches against name, description, id, category, and models', () {
      final state = ProviderBrowserState.initial()
          .copyWith(providers: [presetA, presetB], searchQuery: 'GPT');
      expect(state.filteredProviders.map((p) => p.id), ['openai']);
    });

    test('popularProviders / otherProviders split on category', () {
      final state = ProviderBrowserState.initial().copyWith(providers: [presetA, presetB]);
      expect(state.popularProviders.map((p) => p.id), ['openai']);
      expect(state.otherProviders.map((p) => p.id), ['ollama']);
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails (compile error)**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_browser_state_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/provider_browser_state.dart'`. This is the failing test we want.

- [ ] **Step 3: Create `provider_browser_state.dart`**

Create `client/lib/data/providers/provider_browser_state.dart`:

```dart
import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';

@immutable
class ProviderBrowserState {
  const ProviderBrowserState({
    this.providers = const <ProviderPreset>[],
    this.activeProvider,
    this.validationStatus = const <String, String>{},
    this.modelsMap = const <String, List<String>>{},
    this.loadingModelIds = const <String>{},
    this.isFetching = false,
    this.isValidating = false,
    this.searchQuery = '',
    this.error,
  });

  /// Initial empty state — no providers fetched, no errors.
  const ProviderBrowserState.initial()
      : providers = const <ProviderPreset>[],
        activeProvider = null,
        validationStatus = const <String, String>{},
        modelsMap = const <String, List<String>>{},
        loadingModelIds = const <String>{},
        isFetching = false,
        isValidating = false,
        searchQuery = '',
        error = null;

  final List<ProviderPreset> providers;
  final ProviderPreset? activeProvider;
  final Map<String, String> validationStatus;
  final Map<String, List<String>> modelsMap;
  final Set<String> loadingModelIds;
  final bool isFetching;
  final bool isValidating;
  final String searchQuery;
  final String? error;

  /// Providers filtered by `searchQuery` (case-insensitive across name,
  /// description, id, category, and embedded model ids).
  List<ProviderPreset> get filteredProviders {
    if (searchQuery.trim().isEmpty) return providers;
    final q = searchQuery.toLowerCase().trim();
    return providers.where((p) {
      return p.name.toLowerCase().contains(q) ||
          p.description.toLowerCase().contains(q) ||
          p.id.toLowerCase().contains(q) ||
          p.category.toLowerCase().contains(q) ||
          p.models.any((m) => m.toLowerCase().contains(q));
    }).toList();
  }

  List<ProviderPreset> get popularProviders =>
      filteredProviders.where((p) => p.category == 'popular').toList();

  List<ProviderPreset> get otherProviders =>
      filteredProviders.where((p) => p.category != 'popular').toList();

  ProviderBrowserState copyWith({
    List<ProviderPreset>? providers,
    ProviderPreset? activeProvider,
    bool clearActiveProvider = false,
    Map<String, String>? validationStatus,
    Map<String, List<String>>? modelsMap,
    Set<String>? loadingModelIds,
    bool? isFetching,
    bool? isValidating,
    String? searchQuery,
    String? error,
    bool clearError = false,
  }) {
    return ProviderBrowserState(
      providers: providers ?? this.providers,
      activeProvider:
          clearActiveProvider ? null : (activeProvider ?? this.activeProvider),
      validationStatus: validationStatus ?? this.validationStatus,
      modelsMap: modelsMap ?? this.modelsMap,
      loadingModelIds: loadingModelIds ?? this.loadingModelIds,
      isFetching: isFetching ?? this.isFetching,
      isValidating: isValidating ?? this.isValidating,
      searchQuery: searchQuery ?? this.searchQuery,
      error: clearError ? null : (error ?? this.error),
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ProviderBrowserState &&
        listEquals(other.providers, providers) &&
        other.activeProvider == activeProvider &&
        mapEquals(other.validationStatus, validationStatus) &&
        mapEquals(other.modelsMap, modelsMap) &&
        setEquals(other.loadingModelIds, loadingModelIds) &&
        other.isFetching == isFetching &&
        other.isValidating == isValidating &&
        other.searchQuery == searchQuery &&
        other.error == error;
  }

  @override
  int get hashCode => Object.hash(
        Object.hashAll(providers),
        activeProvider,
        Object.hashAll(validationStatus.entries.map((e) => '${e.key}=${e.value}')),
        Object.hashAll(modelsMap.entries
            .map((e) => '${e.key}=${e.value.join(",")}')),
        Object.hashAll(loadingModelIds),
        isFetching,
        isValidating,
        searchQuery,
        error,
      );
}
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_browser_state_test.dart
```

Expected: **PASS** — all 7 tests green.

- [ ] **Step 5: Run `dart analyze` on the new file**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/data/providers/provider_browser_state.dart test/data/provider_browser_state_test.dart
```

Expected: `No issues found!` for these files (pre-existing analyzer debt elsewhere is fine).

- [ ] **Step 6: Commit**

```bash
cd d:\OmniScribe
git add client/lib/data/providers/provider_browser_state.dart client/test/data/provider_browser_state_test.dart
git commit -m "feat(client): provider browser slice — ProviderBrowserState with copyWith + filtered getters"
```

---

## Task 2: Create `ProviderBrowserNotifier` — build + fetchProviders (TDD)

**Files:**
- Create: `client/lib/data/providers/provider_notifier.dart` (scaffold + build + fetchProviders)
- Test: `client/test/data/provider_notifier_test.dart` (scaffold + first test group)

- [ ] **Step 1: Write the failing test file (part 1)**

Create `client/test/data/provider_notifier_test.dart` with only the `build` and `fetchProviders` groups:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_notifier.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

class _MockProviderRepository extends Mock implements ProviderRepository {}

class _MockConfigRepository extends Mock implements ConfigRepository {}

void main() {
  late _MockProviderRepository repo;
  late _MockConfigRepository configRepo;

  setUp(() {
    repo = _MockProviderRepository();
    configRepo = _MockConfigRepository();
    // Default stubs for the Settings notifier's load() path. Task 4's
    // setActiveProvider test reaches into settingsStateProvider.load()
    // which calls configRepo.getConfig() + getModels(...). The Settings
    // notifier swallows those errors into state.error, so a throw is fine
    // here — we only need the call to NOT crash the test container.
    when(() => configRepo.getConfig())
        .thenThrow(StateError('test stub: configRepo not configured'));
    when(() => configRepo.getModels(namespace: any(named: 'namespace')))
        .thenThrow(StateError('test stub: configRepo not configured'));
  });

  ProviderContainer makeContainer() {
    return ProviderContainer(
      overrides: [
        providerRepositoryProvider.overrideWithValue(repo),
        configRepositoryProvider.overrideWithValue(configRepo),
      ],
    );
  }

  group('ProviderBrowserNotifier.build', () {
    test('returns ProviderBrowserState.initial() before any method call', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(providerBrowserProvider);
      expect(state.providers, isEmpty);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });
  });

  group('ProviderBrowserNotifier.fetchProviders', () {
    test('populates providers list', () async {
      const presetA = ProviderPreset(
        id: 'openai',
        name: 'OpenAI',
        category: 'popular',
        description: 'GPT models',
        recommendedBaseUrl: 'https://api.openai.com/v1',
        defaultModel: 'gpt-4o',
      );
      const presetB = ProviderPreset(
        id: 'template-provider',
        name: 'Template',
        category: 'popular',
        description: 'Uses placeholder',
        recommendedBaseUrl: 'http://{host}/v1', // contains '{' -> skip auto-fetch
        defaultModel: 'm',
      );
      when(() => repo.getProviders()).thenAnswer((_) async => [presetA, presetB]);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchProviders();

      final state = container.read(providerBrowserProvider);
      expect(state.providers, [presetA, presetB]);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });

    test('on failure populates error and clears isFetching', () async {
      when(() => repo.getProviders()).thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchProviders();

      final state = container.read(providerBrowserProvider);
      expect(state.isFetching, isFalse);
      expect(state.providers, isEmpty);
      expect(state.error, contains('boom'));
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails (compile error)**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/provider_notifier.dart'`.

- [ ] **Step 3: Create `provider_notifier.dart` (scaffold + build + fetchProviders)**

Create `client/lib/data/providers/provider_notifier.dart`:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

/// Riverpod entry-point for the Provider Browser feature.
///
/// Wires `data/repositories/provider_repository.dart` to a
/// `ProviderBrowserState` and exposes the same verb set the legacy
/// `state/provider_browser_provider.dart` did:
/// `fetchProviders`, `fetchModelsForProvider`, `validateProvider`,
/// `setActiveProvider`, `setSearchQuery`, `selectActiveProvider`.
final providerBrowserProvider =
    NotifierProvider<ProviderBrowserNotifier, ProviderBrowserState>(
  ProviderBrowserNotifier.new,
);

class ProviderBrowserNotifier extends Notifier<ProviderBrowserState> {
  late final ProviderRepository _repo;

  @override
  ProviderBrowserState build() {
    _repo = ref.watch(providerRepositoryProvider);
    return const ProviderBrowserState.initial();
  }

  Future<void> fetchProviders() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final providers = await _repo.getProviders();
      state = state.copyWith(providers: providers, isFetching: false);
      // Auto-fetch models for providers whose `recommendedBaseUrl` is
      // a concrete URL (no template placeholders like `{host}`).
      for (final provider in providers) {
        if (provider.recommendedBaseUrl.isNotEmpty &&
            !provider.recommendedBaseUrl.contains('<') &&
            !provider.recommendedBaseUrl.contains('{')) {
          // Intentionally not awaited — fire-and-forget; per-provider
          // state updates land via `fetchModelsForProvider`. The legacy
          // behaviour was the same.
          // ignore: unawaited_futures
          fetchModelsForProvider(provider.id);
        }
      }
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }
}
```

> **NOTE:** The `// ignore: unawaited_futures` is a pre-existing project convention used in slice 1 / slice 2 — see `jobs_notifier.dart` for the same shape. The plan's quality bar is "zero NEW `// ignore:` lines without justification" — this is justified because matching legacy behaviour requires it. If your lint set disallows it, the alternative is to wrap in `unawaited(...)` (from `dart:async`) — the implementer subagent picks whichever the project already uses.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **PASS** — `build` group (1 test) and `fetchProviders` group (2 tests) green.

- [ ] **Step 5: Run `dart analyze`**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/data/providers/provider_notifier.dart test/data/provider_notifier_test.dart
```

Expected: `No issues found!` for these files.

- [ ] **Step 6: Commit**

```bash
cd d:\OmniScribe
git add client/lib/data/providers/provider_notifier.dart client/test/data/provider_notifier_test.dart
git commit -m "feat(client): provider browser slice — ProviderBrowserNotifier scaffold + fetchProviders"
```

---

## Task 3: Add `fetchModelsForProvider` to the notifier (TDD)

**Files:**
- Modify: `client/lib/data/providers/provider_notifier.dart`
- Modify: `client/test/data/provider_notifier_test.dart` (append new group)

- [ ] **Step 1: Append the `fetchModelsForProvider` test group to the test file**

Append to `client/test/data/provider_notifier_test.dart` (after the closing `}` of the `fetchProviders` group, before the final `}` of `void main`):

```dart
  group('ProviderBrowserNotifier.fetchModelsForProvider', () {
    test('populates modelsMap and removes the id from loadingModelIds on success', () async {
      when(() => repo.getProviderModels(any())).thenAnswer(
        (_) async => const ProviderModelsResponse(models: ['m1', 'm2']),
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchModelsForProvider('openai');

      final state = container.read(providerBrowserProvider);
      expect(state.modelsMap['openai'], ['m1', 'm2']);
      expect(state.loadingModelIds.contains('openai'), isFalse);
    });

    test('is a no-op when the id is already in loadingModelIds (deduplicates concurrent calls)', () async {
      var callCount = 0;
      when(() => repo.getProviderModels(any())).thenAnswer((_) async {
        callCount += 1;
        // Hold the future open so we can observe the in-flight flag.
        await Future<void>.delayed(const Duration(milliseconds: 20));
        return const ProviderModelsResponse(models: ['m']);
      });

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      // Kick off two concurrent calls; the second should be deduped.
      final f1 = notifier.fetchModelsForProvider('openai');
      final f2 = notifier.fetchModelsForProvider('openai');
      await Future<void>.wait([f1, f2]);

      expect(callCount, 1);
      expect(container.read(providerBrowserProvider).loadingModelIds.contains('openai'), isFalse);
    });

    test('removes the id from loadingModelIds even when the repo throws', () async {
      when(() => repo.getProviderModels(any())).thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.fetchModelsForProvider('openai');

      final state = container.read(providerBrowserProvider);
      expect(state.loadingModelIds.contains('openai'), isFalse);
      expect(state.modelsMap['openai'], isNull);
    });
  });
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **COMPILE FAIL** with `'ProviderBrowserNotifier' doesn't have instance method 'fetchModelsForProvider'`.

- [ ] **Step 3: Add `fetchModelsForProvider` to the notifier**

Replace the entire body of `client/lib/data/providers/provider_notifier.dart` with:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

/// Riverpod entry-point for the Provider Browser feature.
///
/// Wires `data/repositories/provider_repository.dart` to a
/// `ProviderBrowserState` and exposes the same verb set the legacy
/// `state/provider_browser_provider.dart` did:
/// `fetchProviders`, `fetchModelsForProvider`, `validateProvider`,
/// `setActiveProvider`, `setSearchQuery`, `selectActiveProvider`.
final providerBrowserProvider =
    NotifierProvider<ProviderBrowserNotifier, ProviderBrowserState>(
  ProviderBrowserNotifier.new,
);

class ProviderBrowserNotifier extends Notifier<ProviderBrowserState> {
  late final ProviderRepository _repo;

  @override
  ProviderBrowserState build() {
    _repo = ref.watch(providerRepositoryProvider);
    return const ProviderBrowserState.initial();
  }

  Future<void> fetchProviders() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final providers = await _repo.getProviders();
      state = state.copyWith(providers: providers, isFetching: false);
      for (final provider in providers) {
        if (provider.recommendedBaseUrl.isNotEmpty &&
            !provider.recommendedBaseUrl.contains('<') &&
            !provider.recommendedBaseUrl.contains('{')) {
          // ignore: unawaited_futures
          fetchModelsForProvider(provider.id);
        }
      }
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  Future<void> fetchModelsForProvider(String id) async {
    if (state.loadingModelIds.contains(id)) return;

    state = state.copyWith(
      loadingModelIds: {...state.loadingModelIds, id},
    );

    try {
      final response = await _repo.getProviderModels(id);
      final next = Map<String, List<String>>.from(state.modelsMap);
      if (response.models.isNotEmpty) {
        next[id] = response.models;
      }
      state = state.copyWith(
        modelsMap: next,
        loadingModelIds: state.loadingModelIds.difference({id}),
      );
    } catch (_) {
      state = state.copyWith(
        loadingModelIds: state.loadingModelIds.difference({id}),
      );
    }
  }
}
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **PASS** — `build` (1) + `fetchProviders` (2) + `fetchModelsForProvider` (3) = 6 green.

- [ ] **Step 5: Run `dart analyze`**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/data/providers/provider_notifier.dart test/data/provider_notifier_test.dart
```

Expected: `No issues found!` for these files.

- [ ] **Step 6: Commit**

```bash
cd d:\OmniScribe
git add client/lib/data/providers/provider_notifier.dart client/test/data/provider_notifier_test.dart
git commit -m "feat(client): provider browser slice — fetchModelsForProvider with dedup + fail-open"
```

---

## Task 4: Add `validateProvider` + `setActiveProvider` + `setSearchQuery` + `selectActiveProvider` (TDD)

**Files:**
- Modify: `client/lib/data/providers/provider_notifier.dart`
- Modify: `client/test/data/provider_notifier_test.dart` (append new groups)

- [ ] **Step 1: Append the four remaining test groups to the test file**

Append to `client/test/data/provider_notifier_test.dart` (before the final `}` of `void main`):

```dart
  group('ProviderBrowserNotifier.validateProvider', () {
    test('on success populates validationStatus and triggers model refetch', () async {
      when(() => repo.validateProvider(any())).thenAnswer(
        (_) async => const ValidateProviderResponse(valid: true, modelCount: 3),
      );
      when(() => repo.getProviderModels(any())).thenAnswer(
        (_) async => const ProviderModelsResponse(models: ['m1']),
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      final res = await notifier.validateProvider(
        'openai', 'https://api.openai.com/v1', null,
      );

      expect(res.valid, isTrue);
      final state = container.read(providerBrowserProvider);
      expect(state.validationStatus['openai'], contains('3'));
      expect(state.isValidating, isFalse);
    });

    test('on failure populates validationStatus with error and clears isValidating', () async {
      when(() => repo.validateProvider(any())).thenAnswer(
        (_) async => const ValidateProviderResponse(valid: false, error: 'bad creds'),
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      final res = await notifier.validateProvider(
        'openai', 'https://api.openai.com/v1', 'k',
      );

      expect(res.valid, isFalse);
      final state = container.read(providerBrowserProvider);
      expect(state.validationStatus['openai'], 'bad creds');
      expect(state.isValidating, isFalse);
    });
  });

  group('ProviderBrowserNotifier.setActiveProvider', () {
    test('on success calls repo.setActiveProvider, mirrors activeProviderId into settingsStateProvider, and re-fetches settings', () async {
      when(() => repo.setActiveProvider(any())).thenAnswer(
        (_) async => const SetActiveProviderResponse(
          apiBase: 'https://api.openai.com/v1',
          model: 'gpt-4o',
        ),
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await notifier.setActiveProvider(
        'openai', 'https://api.openai.com/v1', 'k', 'gpt-4o',
      );

      final state = container.read(providerBrowserProvider);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
      verify(() => repo.setActiveProvider(any())).called(1);

      // Cross-notifier coordination: settingsStateProvider.activeProviderId
      // should now be 'openai' (mirrored by SettingsNotifier.setActiveProvider).
      expect(container.read(settingsStateProvider).activeProviderId, 'openai');
      // settings.load() was awaited, so configRepo.getConfig was hit.
      verify(() => configRepo.getConfig()).called(greaterThanOrEqualTo(1));
    });

    test('on failure populates error and rethrows without touching settings', () async {
      when(() => repo.setActiveProvider(any())).thenThrow(Exception('reject'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      await expectLater(
        () => notifier.setActiveProvider('openai', null, null, null),
        throwsA(isA<Exception>()),
      );

      final state = container.read(providerBrowserProvider);
      expect(state.isFetching, isFalse);
      expect(state.error, contains('reject'));
      // settings.load() must NOT have been called when the repo throws
      // (otherwise a downstream error would mask the original failure).
      verifyNever(() => configRepo.getConfig());
    });
  });

  group('ProviderBrowserNotifier.setSearchQuery', () {
    test('mirrors the query string into state', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      notifier.setSearchQuery('open');
      expect(container.read(providerBrowserProvider).searchQuery, 'open');
    });
  });

  group('ProviderBrowserNotifier.selectActiveProvider', () {
    test('mirrors the provider into state', () async {
      const preset = ProviderPreset(
        id: 'openai',
        name: 'OpenAI',
        category: 'popular',
        description: '',
        recommendedBaseUrl: '',
        defaultModel: '',
      );

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(providerBrowserProvider.notifier);

      notifier.selectActiveProvider(preset);
      expect(container.read(providerBrowserProvider).activeProvider, preset);

      notifier.selectActiveProvider(null);
      expect(container.read(providerBrowserProvider).activeProvider, isNull);
    });
  });
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **COMPILE FAIL** with `'ProviderBrowserNotifier' doesn't have instance method 'validateProvider'`.

- [ ] **Step 3: Add the four methods to the notifier**

Replace the entire body of `client/lib/data/providers/provider_notifier.dart` with:

```dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';

/// Riverpod entry-point for the Provider Browser feature.
///
/// Wires `data/repositories/provider_repository.dart` to a
/// `ProviderBrowserState` and exposes the same verb set the legacy
/// `state/provider_browser_provider.dart` did:
/// `fetchProviders`, `fetchModelsForProvider`, `validateProvider`,
/// `setActiveProvider`, `setSearchQuery`, `selectActiveProvider`.
final providerBrowserProvider =
    NotifierProvider<ProviderBrowserNotifier, ProviderBrowserState>(
  ProviderBrowserNotifier.new,
);

class ProviderBrowserNotifier extends Notifier<ProviderBrowserState> {
  late final ProviderRepository _repo;

  @override
  ProviderBrowserState build() {
    _repo = ref.watch(providerRepositoryProvider);
    return const ProviderBrowserState.initial();
  }

  Future<void> fetchProviders() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final providers = await _repo.getProviders();
      state = state.copyWith(providers: providers, isFetching: false);
      for (final provider in providers) {
        if (provider.recommendedBaseUrl.isNotEmpty &&
            !provider.recommendedBaseUrl.contains('<') &&
            !provider.recommendedBaseUrl.contains('{')) {
          // ignore: unawaited_futures
          fetchModelsForProvider(provider.id);
        }
      }
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  Future<void> fetchModelsForProvider(String id) async {
    if (state.loadingModelIds.contains(id)) return;

    state = state.copyWith(
      loadingModelIds: {...state.loadingModelIds, id},
    );

    try {
      final response = await _repo.getProviderModels(id);
      final next = Map<String, List<String>>.from(state.modelsMap);
      if (response.models.isNotEmpty) {
        next[id] = response.models;
      }
      state = state.copyWith(
        modelsMap: next,
        loadingModelIds: state.loadingModelIds.difference({id}),
      );
    } catch (_) {
      state = state.copyWith(
        loadingModelIds: state.loadingModelIds.difference({id}),
      );
    }
  }

  Future<ValidateProviderResponse> validateProvider(
    String id,
    String base,
    String? key, {
    String? model,
  }) async {
    state = state.copyWith(isValidating: true);
    try {
      final res = await _repo.validateProvider(
        ValidateProviderRequest(
          providerId: id,
          apiBase: base,
          apiKey: key,
          model: model,
        ),
      );
      final newStatus = Map<String, String>.from(state.validationStatus);
      newStatus[id] = res.valid
          ? 'Connected successfully (${res.modelCount} models)'
          : (res.error ?? 'Validation failed');
      state = state.copyWith(
        validationStatus: newStatus,
        isValidating: false,
      );
      if (res.valid) {
        // ignore: unawaited_futures
        fetchModelsForProvider(id);
      }
      return res;
    } catch (e) {
      final newStatus = Map<String, String>.from(state.validationStatus);
      newStatus[id] = e.toString();
      state = state.copyWith(validationStatus: newStatus, isValidating: false);
      return ValidateProviderResponse(valid: false, error: e.toString());
    }
  }

  Future<void> setActiveProvider(
    String id,
    String? apiBase,
    String? apiKey,
    String? model,
  ) async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      await _repo.setActiveProvider(
        SetActiveProviderRequest(
          providerId: id,
          apiBase: apiBase,
          apiKey: apiKey,
          model: model,
        ),
      );
      // Cross-notifier coordination: mirror the active provider id into
      // the Settings slice so the Settings tab badge / dropdown follow.
      ref.read(settingsStateProvider.notifier).setActiveProvider(id);
      await ref.read(settingsStateProvider.notifier).load();
      state = state.copyWith(isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
      rethrow;
    }
  }

  void setSearchQuery(String query) {
    state = state.copyWith(searchQuery: query);
  }

  void selectActiveProvider(ProviderPreset? provider) {
    state = state.copyWith(
      activeProvider: provider,
      clearActiveProvider: provider == null,
    );
  }
}
```

- [ ] **Step 4: Run the tests to verify they all pass**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test test/data/provider_notifier_test.dart
```

Expected: **PASS** — all 6 groups, all 10 tests green.

- [ ] **Step 5: Run `dart analyze`**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/data/providers/provider_notifier.dart test/data/provider_notifier_test.dart
```

Expected: `No issues found!` for these files.

- [ ] **Step 6: Commit**

```bash
cd d:\OmniScribe
git add client/lib/data/providers/provider_notifier.dart client/test/data/provider_notifier_test.dart
git commit -m "feat(client): provider browser slice — validateProvider + setActiveProvider + setSearchQuery + selectActiveProvider"
```

---

## Task 5: Rewrite `provider_card.dart` to use the new model import

**Files:**
- Modify: `client/lib/presentation/providers/provider_card.dart`

- [ ] **Step 1: Replace the legacy model import**

In `client/lib/presentation/providers/provider_card.dart`, replace the import block at the top (lines 1-6):

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/models/provider.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
```

with:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
```

(`flutter_riverpod` is unused in this file — `ProviderCard` is a `StatefulWidget`. Keep it removed. Wait — the import is there in the existing file but unused. **If the project's lint setup already flags it as unused, drop it.** Otherwise leave it. The implementer subagent runs `dart analyze` after the rewrite; if it complains, remove the `flutter_riverpod` import line. The plan tolerates either outcome.)

- [ ] **Step 2: Verify `dart analyze` is clean for this file**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/presentation/providers/provider_card.dart
```

Expected: `No issues found!` for this file.

- [ ] **Step 3: Commit**

```bash
cd d:\OmniScribe
git add client/lib/presentation/providers/provider_card.dart
git commit -m "refactor(client): provider card — import new data/models/provider_preset"
```

---

## Task 6: Rewrite `provider_modal.dart` to use the new notifier + model

**Files:**
- Modify: `client/lib/presentation/providers/provider_modal.dart`

- [ ] **Step 1: Replace the legacy imports**

In `client/lib/presentation/providers/provider_modal.dart`, replace lines 1-12:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/models/provider.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/state/provider_browser_provider.dart';
import 'package:omniscribe_client/state/provider_browser_state.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_modal.dart';
import 'provider_card.dart';
```

with:

```dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_modal.dart';
import 'provider_card.dart';
```

That is the **only** change — all references to `providerBrowserProvider` resolve to the new NotifierProvider export of the same name. All references to `ProviderPreset`, `ProviderBrowserState`, etc. resolve to the new `data/models/provider_preset.dart` and `data/providers/provider_browser_state.dart`. The rest of the file's logic stays byte-for-byte identical.

- [ ] **Step 2: Verify `dart analyze` is clean for this file**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/presentation/providers/provider_modal.dart
```

Expected: `No issues found!` for this file.

- [ ] **Step 3: Run all tests**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test
```

Expected: pre-existing test failures (`app_shell_test.dart` TranscriptionScreen DropdownButton + `theme_test.dart` google_fonts) remain at their known counts. New / migrated tests should all pass.

- [ ] **Step 4: Commit**

```bash
cd d:\OmniScribe
git add client/lib/presentation/providers/provider_modal.dart
git commit -m "refactor(client): provider modal — import new data/providers/provider_notifier + provider_preset"
```

---

## Task 7: Rewrite `settings_screen.dart` to use the new provider

**Files:**
- Modify: `client/lib/presentation/settings/settings_screen.dart`

- [ ] **Step 1: Locate the legacy imports**

In `client/lib/presentation/settings/settings_screen.dart`, find the imports of `state/provider_browser_provider.dart`, `state/provider_browser_state.dart`, `services/api_client.dart`, and `models/provider.dart`. (Per earlier reads, those exist at the top imports block.)

- [ ] **Step 2: Replace the legacy imports with new equivalents**

For each of the four legacy imports, replace with:

| Legacy import | New import |
|---|---|
| `package:omniscribe_client/state/provider_browser_provider.dart` | `package:omniscribe_client/data/providers/provider_notifier.dart` |
| `package:omniscribe_client/state/provider_browser_state.dart` | (delete — `ProviderBrowserState` is now in `provider_notifier.dart`'s transitive export via `data/providers/provider_browser_state.dart`, but the settings screen doesn't reference it directly — it only references `providerBrowserProvider`, which is exported from `provider_notifier.dart`) |
| `package:omniscribe_client/services/api_client.dart` | (delete — settings screen doesn't actually need `ApiClient` directly; it consumed it transitively) |
| `package:omniscribe_client/models/provider.dart` | (delete — settings screen doesn't reference `ProviderPreset` directly; it only passes `initialProvider: ProviderPreset?` into `ProviderModal.show(...)`, which is now typed against the new model. **Verify** by re-reading lines 130-180 of the settings screen — if a `ProviderPreset?` field or default is declared on the screen, add `import 'package:omniscribe_client/data/models/provider_preset.dart';`.) |

`ref.watch(providerBrowserProvider)` and `ProviderModal.show(context)` call sites stay byte-for-byte identical.

- [ ] **Step 3: Verify `dart analyze` is clean for this file**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze lib/presentation/settings/settings_screen.dart
```

Expected: `No issues found!` for this file. If a compile error says `ProviderPreset` is undefined, add the new `provider_preset.dart` import.

- [ ] **Step 4: Run all tests**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test
```

Expected: pre-existing failures unchanged.

- [ ] **Step 5: Commit**

```bash
cd d:\OmniScribe
git add client/lib/presentation/settings/settings_screen.dart
git commit -m "refactor(client): settings screen — import new providerBrowserProvider + drop legacy state/models imports"
```

---

## Task 8: Delete the legacy files and verify

**Files:**
- Delete: `client/lib/state/provider_browser_provider.dart`
- Delete: `client/lib/state/provider_browser_state.dart`
- Delete: `client/lib/repositories/providers_repository.dart`
- Delete: `client/lib/models/provider.dart`

- [ ] **Step 1: Confirm zero remaining importers**

```bash
cd d:\OmniScribe\client
Select-String -Path "lib\**\*.dart" -Pattern "state/provider_browser|repositories/providers_repository|models/provider\.dart" -SimpleMatch:$false
```

Expected: **no matches** in `lib/`.

```bash
cd d:\OmniScribe\client
Select-String -Path "test\**\*.dart" -Pattern "state/provider_browser|repositories/providers_repository|models/provider\.dart" -SimpleMatch:$false
```

Expected: **no matches** in `test/` either.

If any match remains, fix the importer before deleting.

- [ ] **Step 2: Delete the four legacy files**

```powershell
cd d:\OmniScribe\client
Remove-Item lib\state\provider_browser_provider.dart
Remove-Item lib\state\provider_browser_state.dart
Remove-Item lib\repositories\providers_repository.dart
Remove-Item lib\models\provider.dart
```

- [ ] **Step 3: Run `dart analyze` across the whole client tree**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" analyze
```

Expected: pre-existing 91 analyzer issues unchanged (none in slice 2 files). Zero new issues.

- [ ] **Step 4: Run `dart format --set-exit-if-changed`**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\dart.bat" format --set-exit-if-changed lib test
```

Expected: exit 0. If it exits non-zero, run `dart format lib test` once to format, then re-run the check.

- [ ] **Step 5: Run all tests**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" test
```

Expected: pre-existing test failures unchanged. New / migrated tests pass.

- [ ] **Step 6: Verify `flutter build windows --debug` succeeds**

```bash
cd d:\OmniScribe\client
& "C:\src\flutter\bin\flutter.bat" build windows --debug
```

Expected: `Built build\windows\x64\runner\Debug\runner.exe` (or similar). First build is slow (~5 min); subsequent builds cache.

- [ ] **Step 7: Commit (on local main per user override)**

```bash
cd d:\OmniScribe
git add client/lib/state/provider_browser_provider.dart client/lib/state/provider_browser_state.dart client/lib/repositories/providers_repository.dart client/lib/models/provider.dart
git commit -m "feat(client): provider browser slice — Riverpod NotifierProvider replaces state/provider_browser_*, drops legacy providers_repository + provider model"
```

---

## Self-Review (run before claiming done)

After completing all tasks, walk through this checklist:

- [ ] **`dart analyze` exits 0** for slice 2 files (`dart analyze lib/data/providers/provider_browser_state.dart lib/data/providers/provider_notifier.dart test/data/provider_browser_state_test.dart test/data/provider_notifier_test.dart lib/presentation/providers/provider_card.dart lib/presentation/providers/provider_modal.dart lib/presentation/settings/settings_screen.dart`)
- [ ] **`flutter test` passes** for new tests (`flutter test test/data/provider_browser_state_test.dart test/data/provider_notifier_test.dart`)
- [ ] **`flutter build windows --debug` succeeds**
- [ ] **Zero new relative imports** in the modified files
- [ ] **Zero new `// ignore:` lines without justification** (the two `// ignore: unawaited_futures` in `provider_notifier.dart` are justified — matches legacy fire-and-forget behaviour). If the project's lint set disallows `unawaited_futures` ignores, swap to `unawaited(...)` from `dart:async` and remove the ignores.
- [ ] **No commit was made without user confirmation** (Task 8 step 7 lands on local main per the user's "commit everything to local main" convention established in slice 2 / Jobs).
- [ ] **Diff < 600 lines net** (excluding generated `.dart_tool/` / `build/` / platform folders).

---

## Reference

- **Master spec:** [2026-08-24-flutter-client-consolidation-design.md](../specs/2026-08-24-flutter-client-consolidation-design.md) — slice 2 of the 6-slice plan in §3.2.
- **Pattern references:** slice 1 plan at [2026-08-24-flutter-client-consolidation.md](2026-08-24-flutter-client-consolidation.md) + slice 2 (Jobs) plan at [2026-08-26-client-consolidation-jobs-slice.md](2026-08-26-client-consolidation-jobs-slice.md). Same `Notifier<State>` shape; same TDD cadence.
- **Next slice (3):** Progress state migration (`state/progress_provider.dart` + `state/progress_state.dart` + `models/job_progress_state.dart`). Separate plan when this slice lands.
