# Jobs Slice — Flutter Client Consolidation Slice 2

**Date:** 2026-08-26
**Status:** Approved (pending user review of this spec doc)
**Parent spec:** [2026-08-24-flutter-client-consolidation-design.md](2026-08-24-flutter-client-consolidation-design.md) (slice 2 in this series; numbered 3 in the parent's ordering — see "Re-cut note" below)
**Scope:** `client/` (Flutter desktop client) only.

## Re-cut note (deviation from parent spec)

The parent spec's slice ordering was:

| # | Slice |
|---|---|
| 1 | Settings ✅ shipped |
| 2 | Provider Browser |
| 3 | Job History (Jobs **+ Progress bundled**) |
| 4 | Features |
| 5 | Workstation |
| 6 | Final cleanup |

This slice 2 was originally "Provider Browser". The user re-prioritised to **Jobs** (parent's slice 3) ahead of Provider Browser, and explicitly split the parent's bundled "Job History" into two sub-slices — this spec covers **Jobs only**. Progress moves to a later, dedicated slice. Rationale: Jobs is the smaller vertical; consolidating Provider Browser first (per parent) requires the new `JobRepositoryImpl` to know about provider identity plumbing the data layer doesn't yet need.

## 1. Goals

1. Migrate the Jobs vertical from Stack A (`state/`, `repositories/`, `models/`, `services/`) to Stack B (`data/`, `core/network/`) using Riverpod 2.x `Notifier`.
2. Extend `data/models/job_record.dart` so it is wire-compatible with the legacy `models/job.dart` (the legacy `JobRecord` carries `textArtifactId`/`textArtifactToken` that the existing data model lacks; `JobHistoryScreen` reads `job.textArtifactToken` directly).
3. Add `downloadResult(jobId, token) → Uint8List` to `data/repositories/job_repository.dart` (data-layer repo currently lacks it; legacy has it).
4. Rewrite `presentation/jobs/job_history_screen.dart` to consume the new `jobsProvider` and use the canonical common widgets / theme tokens (mirrors how slice 1 rewrote `settings_screen.dart`).
5. Retire the legacy Jobs files once nothing imports them.

## 2. Non-goals (out of scope)

1. **Progress / WebSocket** — `state/progress_provider.dart` + `state/progress_state.dart` + `models/job_progress_state.dart` + `models/ws_envelope.dart` stay untouched. They get their own slice after this one.
2. **Provider Browser** — `state/provider_browser_provider.dart` + `state/provider_browser_state.dart` + `repositories/providers_repository.dart` + `models/provider.dart` stay untouched; their slice is deferred.
3. **`services/api_client.dart`** — only Jobs' import is removed this slice. Features, Provider Browser, and Progress still depend on `services/api_client.dart`; the file stays until those slices retire their imports. (Same disposition slice 1 took — `services/api_client.dart` was slated for retirement but kept because other importers remained.)
4. **`presentation/views/jobs_view.dart`** — parallel design-system twin using mock data, no `jobsProvider` consumer. Out of scope; eventual slice 6 cleanup.
5. **Phase 2 features** — file picker, drag-drop, local persistence, native desktop polish — all deferred to the parent spec's Phase 2 roadmap.

## 3. Target files

### NEW

| Path | Purpose |
|---|---|
| `client/lib/data/providers/jobs_state.dart` | `JobsState` value class — fields: `List<JobRecord> jobs`, `bool isFetching`, `String? error`. `const JobsState({...})`, `copyWith({...})` with `clearError: bool = false` flag (same shape slice 1 used for `SettingsState`). |
| `client/lib/data/providers/jobs_notifier.dart` | `JobsNotifier extends Notifier<JobsState>` + `final jobsProvider = NotifierProvider<JobsNotifier, JobsState>(JobsNotifier.new)`. `build()` returns `const JobsState()` and `Future.microtask(fetchJobs)`s the first fetch (matches Settings pattern of letting the screen also kick a `ref.read(...notifier).fetchJobs()` from `initState` so pull-to-refresh works). |
| `client/test/data/jobs_state_test.dart` | Tests for `JobsState.copyWith` semantics + initial empty state. |
| `client/test/data/jobs_notifier_test.dart` | mocktail tests for `fetchJobs` / `clearJobs` / `cancelJob` / `downloadResult` (success + failure paths). |

### MODIFIED

| Path | Change |
|---|---|
| `client/lib/data/models/job_record.dart` | Add `final String? textArtifactId;` + `final String? textArtifactToken;` fields to `JobRecord`; add to constructor (defaulted `null`); parse `text_artifact_id` / `text_artifact_token` keys in `JobRecord.fromJson`; emit in `toJson` when non-null. **No other fields change.** |
| `client/lib/data/repositories/job_repository.dart` | Add abstract `Future<Uint8List> downloadResult(String jobId, String token);` to `JobRepository`; implement in `JobRepositoryImpl` using `_apiClient.getBytes` against `ApiConstants.jobResult(jobId)` with `{token}` query param and `Authorization: Bearer <token>` header when token is non-empty (mirrors legacy `JobsRepository.downloadResult`). Add `ApiConstants.jobResult(jobId)` if it doesn't already exist; otherwise use `/api/jobs/{jobId}/result`. |
| `client/lib/presentation/jobs/job_history_screen.dart` | Rewrite to `ConsumerStatefulWidget` consuming `jobsProvider` (`ref.watch(jobsProvider)` for state, `ref.read(jobsProvider.notifier).{fetchJobs,clearJobs,cancelJob,downloadResult}` for actions). Switch imports from `package:omniscribe_client/state/jobs_provider.dart` + `models/job.dart` + `theme/docuverse_theme.dart` + `presentation/widgets/docuverse_*` to `data/providers/jobs_notifier.dart` + `data/models/job_record.dart` + `core/theme/app_theme.dart` + `presentation/common/app_*` widgets. Preserve all existing UX: header row with badge, Refresh button, Clear all button, status banner (info/error tinting), main `DataTable` with Job ID / Status / Filename / Pipeline+Model / Duration / Failed Pages / Actions columns, Cancel button while running, PDF download button when complete, error-banner surfacing. |

### DELETED (after this slice lands + zero importers)

| Path | Replaced by |
|---|---|
| `client/lib/state/jobs_provider.dart` | `client/lib/data/providers/jobs_notifier.dart` |
| `client/lib/state/jobs_state.dart` | `client/lib/data/providers/jobs_state.dart` |
| `client/lib/repositories/jobs_repository.dart` | `client/lib/data/repositories/job_repository.dart` |
| `client/lib/models/job.dart` | `client/lib/data/models/job_record.dart` (after `textArtifactId` / `textArtifactToken` extension) |

## 4. Shapes

### `JobsState`

```dart
class JobsState {
  const JobsState({
    this.jobs = const <JobRecord>[],
    this.isFetching = false,
    this.error,
  });

  final List<JobRecord> jobs;
  final bool isFetching;
  final String? error;

  JobsState copyWith({
    List<JobRecord>? jobs,
    bool? isFetching,
    String? error,
    bool clearError = false,
  }) {
    return JobsState(
      jobs: jobs ?? this.jobs,
      isFetching: isFetching ?? this.isFetching,
      error: clearError ? null : (error ?? this.error),
    );
  }
}
```

### `JobsNotifier`

```dart
final jobsProvider = NotifierProvider<JobsNotifier, JobsState>(
  JobsNotifier.new,
);

class JobsNotifier extends Notifier<JobsState> {
  late final JobRepository _repo;

  @override
  JobsState build() {
    _repo = ref.watch(jobRepositoryProvider);
    return const JobsState();
  }

  Future<void> fetchJobs() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final jobs = await _repo.listJobs();
      state = state.copyWith(jobs: jobs, isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  Future<void> clearJobs() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      await _repo.clearJobs();
      state = state.copyWith(jobs: const <JobRecord>[], isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> cancelJob(String jobId) async {
    try {
      await _repo.cancelJob(jobId);
      await fetchJobs();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      rethrow;
    }
  }

  Future<Uint8List> downloadResult(String jobId, String token) async {
    try {
      return await _repo.downloadResult(jobId, token);
    } catch (e) {
      state = state.copyWith(error: e.toString());
      rethrow;
    }
  }
}
```

### `data/models/job_record.dart` — `JobRecord` additions

```dart
class JobRecord {
  const JobRecord({
    required this.id,
    required this.filename,
    required this.model,
    required this.pipelineMode,
    required this.durationS,
    required this.timestamp,
    required this.status,
    this.pages,
    this.failedPages = const <int>[],
    this.textArtifactId,
    this.textArtifactToken,   // NEW
  });

  // ... existing fields ...
  final String? textArtifactId;     // NEW
  final String? textArtifactToken;  // NEW

  factory JobRecord.fromJson(Map<String, dynamic> json) {
    return JobRecord(
      id: json['id']?.toString() ?? '',
      filename: json['filename']?.toString() ?? '',
      model: json['model']?.toString() ?? '',
      pipelineMode: json['pipeline_mode']?.toString() ?? '',
      durationS: (json['duration_s'] as num?)?.toDouble() ?? 0.0,
      timestamp: json['timestamp']?.toString() ?? '',
      status: json['status']?.toString() ?? 'unknown',
      pages: json['pages']?.toString(),
      failedPages: _parseFailedPages(json['failed_pages']),
      textArtifactId: json['text_artifact_id']?.toString(),     // NEW
      textArtifactToken: json['text_artifact_token']?.toString(), // NEW
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'filename': filename,
        'model': model,
        'pipeline_mode': pipelineMode,
        'duration_s': durationS,
        'timestamp': timestamp,
        'status': status,
        if (pages != null) 'pages': pages,
        'failed_pages': failedPages,
        if (textArtifactId != null) 'text_artifact_id': textArtifactId,         // NEW
        if (textArtifactToken != null) 'text_artifact_token': textArtifactToken, // NEW
      };
}
```

The legacy `models/job.dart` `JobRecord.fromJson` did `json['id'] as String? ?? json['job_id'] as String? ?? ''` and similar fallbacks. The data-layer version does `json['id']?.toString() ?? ''` which is more permissive (accepts non-string `id`). **No behaviour change for the wire format** — server-side jobs return `id` as a string. The legacy code's `id ?? job_id` fallback is a defensive only-on-error convenience; if anyone relied on it, the only risk is a job without `id` falling back to `''` instead of also checking `job_id`. **This slice accepts that risk** because the documented backend contract uses `id`. (Documented under "Risks" below.)

### `data/repositories/job_repository.dart` — `downloadResult` addition

```dart
abstract class JobRepository {
  Future<List<JobRecord>> listJobs();
  Future<int> clearJobs();
  Future<bool> cancelJob(String jobId);
  Future<Uint8List> downloadResult(String jobId, String token);  // NEW
}

class JobRepositoryImpl implements JobRepository {
  // ... existing ...

  @override
  Future<Uint8List> downloadResult(String jobId, String token) async {
    final headers = <String, String>{};
    if (token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return _apiClient.getBytes<Uint8List>(
      ApiConstants.jobResult(jobId),
      queryParams: {'token': token},
      headers: headers,
    );
  }
}
```

`ApiConstants.jobResult(jobId)` — verify it exists in `core/constants/api_constants.dart`; if not, add `/api/jobs/{jobId}/result` as the path.

`_apiClient.getBytes` — verify the signature on `core/network/api_client.dart` (the legacy call used `_apiClient.getBytes('/jobs/$jobId/result', queryParams: {'token': token}, headers: headers)` returning `Uint8List`). If signature differs, adapt.

## 5. Screen rewrite — `presentation/jobs/job_history_screen.dart`

Behaviour to preserve (from current 371-line implementation):

1. **Header row** — title "Job Execution History", badge with `jobs.length`, subtitle, Refresh button (loading state bound to `isFetching`), Clear all button (disabled when `jobs` is empty).
2. **Status banner** — shows after a download or cancel; tints `tokens.danger` when message contains "error", `tokens.info` otherwise; auto-clears on next action.
3. **Main `DataTable`** — columns: Job ID (truncated to 8 chars + ellipsis, monospace), Status (badge with variant per status), Filename (constrained 160px, ellipsis), Pipeline / Model (monospace), Duration (seconds to 1dp, `—` if 0), Failed Pages (badge of joined page numbers, or `None`), Actions (Cancel when `processing|pending`, PDF download when `complete|completed|success|failed|error|cancelled|other`).
4. **Empty state** — Centered Icon + text "Loading job history…" when `isFetching`, "No historical OCR or translation jobs found." otherwise.
5. **Local download handling** — `_downloadingJobId` tracks per-row spinner; on success shows "Downloaded searchable PDF for {filename} ({bytes.lengthInBytes} bytes)"; on error shows "Download error: {e}".

Visual surface changes (from old `docuverse_*` widgets to new common widgets):

- `Scaffold(body: Padding(...))` → `Scaffold(body: SafeArea(child: Padding(...)))` (matches `settings_screen.dart` post-slice-1 shape).
- `DocuVerseBadge` → `AppBadge` with `label` parameter.
- `DocuVerseButton` → `AppButton` with `label`, `variant`, `loading`, `icon`.
- `DocuVerseCard` → `AppCard` with `padding: AppCardPadding.none`.
- `DocuVerseModal.show` → `AppModal.show` (or `showAppModal` helper if it exists in `common/app_modal.dart` — verify before writing).
- Theme tokens: `context.docuVerse` → `context.colors` / `context.typography` (the new pattern from slice 1).

The screen rewrite does not change UX flow, only the widget surface. Same data, same layout.

## 6. Tests

### `jobs_state_test.dart` (mirrors `settings_state_test.dart`)

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/providers/jobs_state.dart';
import 'package:omniscribe_client/data/models/job_record.dart';

void main() {
  group('JobsState', () {
    test('default constructor returns empty list, not fetching, no error', () {
      const state = JobsState();
      expect(state.jobs, isEmpty);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });

    test('copyWith preserves untouched fields', () {
      const before = JobsState();
      final after = before.copyWith(isFetching: true);
      expect(after.isFetching, isTrue);
      expect(after.jobs, before.jobs);
      expect(after.error, before.error);
    });

    test('clearError: null error preserved when explicit null passed', () {
      const before = JobsState(error: 'boom');
      final after = before.copyWith(clearError: true);
      expect(after.error, isNull);
    });

    test('jobs list is replaced (not merged) by copyWith', () {
      final a = JobsRecord.fromJson(<String, dynamic>{'id': 'a'});
      final b = JobsRecord.fromJson(<String, dynamic>{'id': 'b'});
      const before = JobsState();
      final after = before.copyWith(jobs: [a, b]);
      expect(after.jobs, [a, b]);
    });
  });
}
```

### `jobs_notifier_test.dart` (mirrors `settings_notifier_test.dart`)

mocktail `_MockJobRepository implements JobRepository`. Override `jobRepositoryProvider` in a `ProviderContainer`. Cover:

- `build()` returns `const JobsState()` with empty jobs, `isFetching: false`, `error: null`.
- `fetchJobs()` on success — calls `repo.listJobs()` once, sets `state.jobs` to result, `isFetching: false`, `error: null`.
- `fetchJobs()` on `repo.listJobs()` throwing — sets `state.error` to the message, `isFetching: false`, `jobs` unchanged.
- `clearJobs()` on success — calls `repo.clearJobs()`, resets `state.jobs` to empty list, `isFetching: false`.
- `clearJobs()` on failure — sets `state.error`, rethrows so the screen can show its banner.
- `cancelJob(id)` on success — calls `repo.cancelJob(id)`, then re-fetches via `fetchJobs()`.
- `cancelJob(id)` on failure — sets `state.error`, rethrows; does **not** call `fetchJobs()`.
- `downloadResult(id, token)` on success — returns bytes from repo, does not modify `state`.
- `downloadResult(id, token)` on failure — sets `state.error`, rethrows.

## 7. Slice invariants (must hold at the end)

- The slice's screen builds and runs against the live OmniScribe backend (or, when offline, the empty-state path renders without throwing).
- `dart analyze` reports zero new issues introduced by the slice.
- `flutter test` passes both new test files plus all existing tests.
- The slice adds two test files (`jobs_state_test.dart`, `jobs_notifier_test.dart`) covering reducer logic and notifier behavior.
- No `// ignore: ...` lines added without justification.
- No new relative imports introduced; everything uses `package:omniscribe_client/...`.
- `state/jobs_*.dart`, `repositories/jobs_repository.dart`, `models/job.dart` are deleted; `grep -r 'state/jobs_\|repositories/jobs_repository\|models/job\.dart' client/` returns zero hits.

## 8. Risks

1. **`JobRecord` field-name fallback divergence** — legacy `models/job.dart` had `id ?? job_id`, `timestamp ?? created_at` defensive fallbacks. The data-layer model uses single-key access with `.toString()` fallback. If any backend response ever sends `job_id` without `id`, the data-layer model will produce empty-string ids. Mitigation: read the backend's `/api/jobs` route to confirm it sends `id`; if `job_id` is also possible, add the fallback to `JobRecord.fromJson`.
2. **`ApiClient.getBytes` signature** — verify `core/network/api_client.dart` exposes `getBytes<T>(String path, {Map<String, String>? queryParams, Map<String, String>? headers})` returning `Future<T>`. If not, adapt `downloadResult` to the actual signature (likely `getBytes(String path, {...}) → Future<Uint8List>` without generics).
3. **`flutter` not on PATH** — prior sessions reported `flutter` not in `$env:PATH` and not findable under `C:\Users\rahin`. If `flutter analyze` / `flutter test` cannot run this session, the gate will be verified by code review + manual diff audit (no source-level Dart changes are introduced that the analyzer couldn't see).
4. **`AppModal` API differences** — the legacy `DocuVerseModal.show(context, title, description, maxWidth, actions, child)` may not have a 1:1 equivalent in `presentation/common/app_modal.dart`. Verify the new modal API before writing the rewrite; if it differs significantly, use whatever helper exists and document any UX delta.

## 9. Out of scope (deferred to later slices)

- Progress / WebSocket (`state/progress_*`, `models/job_progress_state.dart`, `models/ws_envelope.dart`) — dedicated slice.
- Provider Browser — slice 2 in the parent spec; deferred.
- Features (translation / transcription / glossary / extraction) — slice 4 in the parent spec.
- Workstation (`document_provider`, `document_view_model`, etc.) — slice 5 in the parent spec.
- Final cleanup (deleting `lib/state/`, `lib/models/`, `lib/repositories/`, `lib/services/` once empty) — slice 6 in the parent spec.
- `presentation/views/jobs_view.dart` — mock-data design-system twin; no `jobsProvider` consumer; eventual slice 6 cleanup.

## 10. Verification commands

```bash
# Run after the slice is implemented:
flutter analyze                                  # must exit 0
flutter test                                     # all existing + new tests must pass
flutter test test/data/jobs_state_test.dart -v   # new
flutter test test/data/jobs_notifier_test.dart -v # new
flutter build windows --debug                    # if flutter on PATH

# Final audit:
grep -r 'state/jobs_\|repositories/jobs_repository\|models/job\.dart' client/lib/   # must return nothing
```

If `flutter` is not on PATH: run a code-review audit confirming (a) no legacy imports remain in `client/lib/`, (b) all four DELETE files are gone, (c) the two NEW files have the expected public API (Notifier extends Notifier, NotifierProvider exposure, method signatures matching the spec), (d) the MODIFIED files preserve their behaviour.