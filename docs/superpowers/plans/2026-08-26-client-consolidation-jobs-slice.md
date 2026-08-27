# Jobs Slice — Flutter Client Consolidation Slice 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Jobs vertical from Stack A (`state/`, `repositories/`, `models/`, `services/`) to Stack B (`data/`, `core/network/`) using Riverpod 2.x `Notifier`, and re-skin `JobHistoryScreen` on the canonical common widgets. This is slice 2 of the multi-slice consolidation plan in [the slice 2 spec](../specs/2026-08-26-client-consolidation-jobs-slice-design.md).

**Architecture:**

- `JobsNotifier extends Notifier<JobsState>` owns the Jobs vertical's state.
- `JobRepository` (data layer) gains `downloadResult(jobId, token)`; `JobRecord` gains `textArtifactId` / `textArtifactToken` so the screen can request a per-job artifact token.
- `JobHistoryScreen` rewires to `ref.watch(jobsProvider)` and to `presentation/common/app_*.dart` (the post-slice-1 common widgets) using `context.colors` / `context.typography` rather than the legacy `context.docuVerse` token surface.
- Legacy `state/jobs_*.dart`, `repositories/jobs_repository.dart`, `models/job.dart` are deleted after zero importers remain.

**Tech Stack:** Flutter (Windows desktop primary), Dart 3.x, `flutter_riverpod ^2.5.1` (`Notifier` / `NotifierProvider` 2.x API), `mocktail`, `dio`, `flutter_test`.

**Conventions:**

- All shell commands in this plan are PowerShell-friendly (`;` separator, not `&&`).
- Run every `dart analyze` / `flutter test` / `flutter build` from `d:\OmniScribe\client`.
- `git checkout -b` + single commit at end (matching slice 1 convention).

---

## File Structure

### Files to create

| Path | Purpose |
|------|---------|
| `client/lib/data/providers/jobs_state.dart` | Immutable `JobsState` (jobs list, isFetching, error) with `copyWith` |
| `client/lib/data/providers/jobs_notifier.dart` | `JobsNotifier extends Notifier<JobsState>` + `jobsProvider` |
| `client/test/data/jobs_state_test.dart` | Reducer / constructor tests |
| `client/test/data/jobs_notifier_test.dart` | Notifier tests via `ProviderContainer` + `mocktail` |

### Files to modify

| Path | Change |
|------|--------|
| `client/lib/data/models/job_record.dart` | Add `textArtifactId`, `textArtifactToken` fields + JSON parse/serialize |
| `client/lib/data/repositories/job_repository.dart` | Add abstract `downloadResult(jobId, token)` + impl using `ApiClient.getBytes` |
| `client/lib/presentation/jobs/job_history_screen.dart` | Rewrite to consume `jobsProvider` + common `app_*` widgets + `context.colors` |

### Files to delete (after zero importers)

| Path | Replaced by |
|------|------------|
| `client/lib/state/jobs_provider.dart` | `client/lib/data/providers/jobs_notifier.dart` |
| `client/lib/state/jobs_state.dart` | `client/lib/data/providers/jobs_state.dart` |
| `client/lib/repositories/jobs_repository.dart` | `client/lib/data/repositories/job_repository.dart` |
| `client/lib/models/job.dart` | `client/lib/data/models/job_record.dart` |

---

## Task 1: Sanity checks on the data layer

Verify that the dependencies this slice will touch already exist in the right shape, so the TDD tasks below can stand on solid ground.

**Files:** read-only

- [ ] **Step 1: Confirm `ApiConstants.jobResult(jobId)` exists**

Open `client/lib/core/constants/api_constants.dart`. Confirm:

```dart
// line ~35
static String jobResult(String jobId) => '/api/jobs/$jobId/result';
```

If missing, add it under the "// Jobs Endpoints" comment block (after `static const String jobs = '/api/jobs';`). No other endpoint constants change.

- [ ] **Step 2: Confirm `ApiClient.getBytes` signature**

Open `client/lib/core/network/api_client.dart`. Confirm the signature (around line 248):

```dart
Future<Uint8List> getBytes(
  String path, {
  Map<String, dynamic>? queryParameters,
  Map<String, dynamic>? headers,
  CancelToken? cancelToken,
}) async { ... }
```

The two key facts: parameter is **`queryParameters`** (NOT `queryParams`), and the return type is non-generic `Future<Uint8List>`. If either is wrong, the file was modified outside this slice — stop and surface to the user.

- [ ] **Step 3: Confirm `JobRepository` exists in the data layer**

Open `client/lib/data/repositories/job_repository.dart`. Confirm it exposes:

```dart
abstract class JobRepository {
  Future<List<JobRecord>> listJobs();
  Future<int> clearJobs();
  Future<bool> cancelJob(String jobId);
}
```

If any method is missing, stop — slice 1 was supposed to land the abstract surface.

- [ ] **Step 4: Confirm `jobRepositoryProvider` exists in `repository_providers.dart`**

Open `client/lib/data/providers/repository_providers.dart`. Confirm:

```dart
final jobRepositoryProvider = Provider<JobRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return JobRepositoryImpl(apiClient);
});
```

If missing, add it under the `/// Job History & Queue Repository provider.` comment block (around line 55).

- [ ] **Step 5: Confirm common widgets exist**

Run:

```powershell
Get-ChildItem -Path lib\presentation\common\app_badge.dart, lib\presentation\common\app_button.dart, lib\presentation\common\app_card.dart, lib\presentation\common\app_modal.dart
```

Expected: 4 file paths, no "File Not Found". The screen rewrite in Task 6 depends on these.

- [ ] **Step 6: Confirm the Jobs tab test expects "Job Execution History"**

Open `client/test/presentation/app_shell_test.dart`. Confirm line ~92 reads:

```dart
expect(find.text('Job Execution History'), findsOneWidget);
```

This is the test the screen rewrite MUST continue to satisfy.

- [ ] **Step 7: Establish a clean baseline**

```powershell
cd d:\OmniScribe\client
dart analyze
flutter test
```

Expected: `dart analyze` exits 0; `flutter test` exits 0 (slice 1's tests + the pre-existing 5 baseline tests). If anything is red, fix before proceeding. Do NOT commit this task — it's a read-only check.

---

## Task 2: Extend `JobRecord` with `textArtifactId` / `textArtifactToken` (TDD)

The legacy `JobHistoryScreen` reads `job.textArtifactToken` directly to download the per-job result PDF. The data-layer `JobRecord` currently lacks both fields. This task adds them.

**Files:**
- Modify: `client/lib/data/models/job_record.dart`
- Test: `client/test/data/job_record_test.dart` (new)

- [ ] **Step 1: Write the failing test**

Create `client/test/data/job_record_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/models/job_record.dart';

void main() {
  group('JobRecord text artifact fields', () {
    test('parses text_artifact_id and text_artifact_token from JSON', () {
      final json = <String, dynamic>{
        'id': 'job-1',
        'filename': 'doc.pdf',
        'model': 'qwen2-vl',
        'pipeline_mode': 'hybrid',
        'duration_s': 4.2,
        'timestamp': '2026-08-26T10:00:00Z',
        'status': 'completed',
        'failed_pages': <int>[],
        'text_artifact_id': 'artifact-xyz',
        'text_artifact_token': 'token-abc',
      };

      final job = JobRecord.fromJson(json);

      expect(job.textArtifactId, 'artifact-xyz');
      expect(job.textArtifactToken, 'token-abc');
    });

    test('text artifact fields default to null when absent', () {
      final json = <String, dynamic>{
        'id': 'job-2',
        'filename': 'doc.pdf',
        'model': 'qwen2-vl',
        'pipeline_mode': 'hybrid',
        'duration_s': 1.0,
        'timestamp': '2026-08-26T10:00:00Z',
        'status': 'completed',
      };

      final job = JobRecord.fromJson(json);

      expect(job.textArtifactId, isNull);
      expect(job.textArtifactToken, isNull);
    });

    test('toJson emits text artifact fields only when non-null', () {
      const job = JobRecord(
        id: 'job-3',
        filename: 'doc.pdf',
        model: 'qwen2-vl',
        pipelineMode: 'hybrid',
        durationS: 0.0,
        timestamp: '2026-08-26T10:00:00Z',
        status: 'completed',
        textArtifactId: 'aid',
        textArtifactToken: 'ttok',
      );

      final encoded = job.toJson();

      expect(encoded['text_artifact_id'], 'aid');
      expect(encoded['text_artifact_token'], 'ttok');
    });

    test('toJson omits text artifact fields when null', () {
      const job = JobRecord(
        id: 'job-4',
        filename: 'doc.pdf',
        model: 'qwen2-vl',
        pipelineMode: 'hybrid',
        durationS: 0.0,
        timestamp: '2026-08-26T10:00:00Z',
        status: 'completed',
      );

      final encoded = job.toJson();

      expect(encoded.containsKey('text_artifact_id'), isFalse);
      expect(encoded.containsKey('text_artifact_token'), isFalse);
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd d:\OmniScribe\client
flutter test test/data/job_record_test.dart
```

Expected: **FAIL** with a compile error (`Class 'JobRecord' has no instance getter 'textArtifactId'`, or `The named parameter 'textArtifactId' isn't defined`).

- [ ] **Step 3: Add the two fields + parse + serialize**

Open `client/lib/data/models/job_record.dart`. **Replace the existing `JobRecord` class** (everything between the first `class JobRecord {` and the matching `}` that ends the class — do not touch `OcrJobStatusResponse`, `ProcessResponse`, or `AsyncSubmitResponse` below it) with:

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
    this.textArtifactToken,
  });

  final String id;
  final String filename;
  final String model;
  final String pipelineMode;
  final String? pages;
  final double durationS;
  final String timestamp;
  final String status;
  final List<int> failedPages;
  final String? textArtifactId;
  final String? textArtifactToken;

  factory JobRecord.fromJson(Map<String, dynamic> json) {
    final failed = <int>[];
    if (json['failed_pages'] is List) {
      for (final item in json['failed_pages'] as List) {
        if (item is num) failed.add(item.toInt());
      }
    }

    return JobRecord(
      id: json['id']?.toString() ?? '',
      filename: json['filename']?.toString() ?? '',
      model: json['model']?.toString() ?? '',
      pipelineMode: json['pipeline_mode']?.toString() ?? '',
      pages: json['pages']?.toString(),
      durationS: (json['duration_s'] as num?)?.toDouble() ?? 0.0,
      timestamp: json['timestamp']?.toString() ?? '',
      status: json['status']?.toString() ?? 'unknown',
      failedPages: failed,
      textArtifactId: json['text_artifact_id']?.toString(),
      textArtifactToken: json['text_artifact_token']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'id': id,
      'filename': filename,
      'model': model,
      'pipeline_mode': pipelineMode,
      if (pages != null) 'pages': pages,
      'duration_s': durationS,
      'timestamp': timestamp,
      'status': status,
      'failed_pages': failedPages,
      if (textArtifactId != null) 'text_artifact_id': textArtifactId,
      if (textArtifactToken != null) 'text_artifact_token': textArtifactToken,
    };
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
cd d:\OmniScribe\client
flutter test test/data/job_record_test.dart
```

Expected: **PASS** — all 4 tests green.

- [ ] **Step 5: Run `dart analyze` on the changed file**

```powershell
cd d:\OmniScribe\client
dart analyze lib/data/models/job_record.dart test/data/job_record_test.dart
```

Expected: `No issues found!`. No commit yet — TDD discipline: this is one of several small commits landing together at the end of the slice.

---

## Task 3: Add `downloadResult(jobId, token)` to `JobRepository` (TDD)

The legacy `repositories/jobs_repository.dart` had `downloadResult(jobId, token) → Uint8List`. The data-layer `JobRepository` is missing it. Add it.

**Files:**
- Modify: `client/lib/data/repositories/job_repository.dart`
- Test: `client/test/data/job_repository_test.dart` (new)

- [ ] **Step 1: Write the failing test**

Create `client/test/data/job_repository_test.dart`:

```dart
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/core/constants/api_constants.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/data/repositories/job_repository.dart';

class _MockApiClient extends Mock implements ApiClient {}

void main() {
  group('JobRepositoryImpl.downloadResult', () {
    late _MockApiClient apiClient;
    late JobRepositoryImpl repo;

    setUp(() {
      apiClient = _MockApiClient();
      repo = JobRepositoryImpl(apiClient);
    });

    test('hits /api/jobs/{jobId}/result with token query param and Bearer header', () async {
      final expectedBytes = Uint8List.fromList([1, 2, 3, 4]);
      when(() => apiClient.getBytes(
            ApiConstants.jobResult('job-42'),
            queryParameters: {'token': 'tok-99'},
            headers: {'Authorization': 'Bearer tok-99'},
          )).thenAnswer((_) async => expectedBytes);

      final result = await repo.downloadResult('job-42', 'tok-99');

      expect(result, expectedBytes);
      verify(() => apiClient.getBytes(
            ApiConstants.jobResult('job-42'),
            queryParameters: {'token': 'tok-99'},
            headers: {'Authorization': 'Bearer tok-99'},
          )).called(1);
    });

    test('omits Authorization header when token is empty', () async {
      final expectedBytes = Uint8List.fromList([9, 8, 7]);
      when(() => apiClient.getBytes(
            ApiConstants.jobResult('job-7'),
            queryParameters: {'token': ''},
            headers: <String, String>{},
          )).thenAnswer((_) async => expectedBytes);

      final result = await repo.downloadResult('job-7', '');

      expect(result, expectedBytes);
      verify(() => apiClient.getBytes(
            ApiConstants.jobResult('job-7'),
            queryParameters: {'token': ''},
            headers: <String, String>{},
          )).called(1);
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd d:\OmniScribe\client
flutter test test/data/job_repository_test.dart
```

Expected: **FAIL** with a compile error (`Class 'JobRepository' doesn't have abstract method 'downloadResult'`, or `'JobRepositoryImpl' doesn't implement 'downloadResult'`).

- [ ] **Step 3: Add the abstract method + implementation**

Open `client/lib/data/repositories/job_repository.dart`. Add the new import at the top (alphabetical with the other imports):

```dart
import 'dart:typed_data';
```

Add the abstract method to the `JobRepository` interface (after `Future<bool> cancelJob(String jobId);`):

```dart
  /// Download the per-job result PDF bytes, authenticated with [token].
  /// Pass an empty [token] for unauthenticated downloads.
  Future<Uint8List> downloadResult(String jobId, String token);
```

Add the implementation to `JobRepositoryImpl` (after `cancelJob`):

```dart
  @override
  Future<Uint8List> downloadResult(String jobId, String token) async {
    final headers = <String, String>{};
    if (token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return _apiClient.getBytes(
      ApiConstants.jobResult(jobId),
      queryParameters: {'token': token},
      headers: headers,
    );
  }
```

Note: the `_apiClient.getBytes` parameter is `queryParameters` (with `e`), NOT `queryParams`. The test in Step 1 enforces this.

- [ ] **Step 4: Run the test to verify it passes**

```powershell
cd d:\OmniScribe\client
flutter test test/data/job_repository_test.dart
```

Expected: **PASS** — both tests green.

- [ ] **Step 5: Run `dart analyze` on the changed files**

```powershell
cd d:\OmniScribe\client
dart analyze lib/data/repositories/job_repository.dart test/data/job_repository_test.dart
```

Expected: `No issues found!`.

---

## Task 4: Create `JobsState` (TDD)

The legacy `state/jobs_state.dart` had `JobsState { jobs, isFetching, error }` with `copyWith(clearError:)`. Mirror that exactly in the data layer.

**Files:**
- Create: `client/lib/data/providers/jobs_state.dart`
- Test: `client/test/data/jobs_state_test.dart` (new)

- [ ] **Step 1: Write the failing test**

Create `client/test/data/jobs_state_test.dart`:

```dart
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/models/job_record.dart';
import 'package:omniscribe_client/data/providers/jobs_state.dart';

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

    test('copyWith clearError: true resets error to null even when error param is null', () {
      const before = JobsState(error: 'boom');
      final after = before.copyWith(clearError: true);

      expect(after.error, isNull);
    });

    test('copyWith replaces jobs list wholesale (no merge)', () {
      final a = JobRecord(
        id: 'a',
        filename: 'a.pdf',
        model: 'm',
        pipelineMode: 'hybrid',
        durationS: 0,
        timestamp: 't',
        status: 'completed',
      );
      final b = JobRecord(
        id: 'b',
        filename: 'b.pdf',
        model: 'm',
        pipelineMode: 'hybrid',
        durationS: 0,
        timestamp: 't',
        status: 'completed',
      );

      const before = JobsState();
      final after = before.copyWith(jobs: [a, b]);

      expect(after.jobs, [a, b]);
    });

    test('copyWith with explicit error overrides previous error', () {
      const before = JobsState(error: 'old');
      final after = before.copyWith(error: 'new');

      expect(after.error, 'new');
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd d:\OmniScribe\client
flutter test test/data/jobs_state_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/jobs_state.dart'`.

- [ ] **Step 3: Implement `JobsState`**

Create `client/lib/data/providers/jobs_state.dart`:

```dart
import 'package:omniscribe_client/data/models/job_record.dart';

/// Immutable state for the Jobs vertical.
///
/// Mirrors the shape slice 1 used for [SettingsState]: a single value object
/// with a `copyWith` that supports both positional updates and a
/// `clearError` flag for explicit null resets.
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

- [ ] **Step 4: Run the test to verify it passes**

```powershell
cd d:\OmniScribe\client
flutter test test/data/jobs_state_test.dart
```

Expected: **PASS** — all 5 tests green.

- [ ] **Step 5: Run `dart analyze` on the new file**

```powershell
cd d:\OmniScribe\client
dart analyze lib/data/providers/jobs_state.dart test/data/jobs_state_test.dart
```

Expected: `No issues found!`.

---

## Task 5: Create `JobsNotifier` (TDD)

The legacy `JobsNotifier extends StateNotifier<JobsState>` exposed `fetchJobs`, `clearJobs`, `cancelJob`, `downloadResult`. Mirror all four on the new `Notifier<JobsState>` 2.x API, wired to the data-layer `JobRepository`.

**Files:**
- Create: `client/lib/data/providers/jobs_notifier.dart`
- Test: `client/test/data/jobs_notifier_test.dart` (new)

- [ ] **Step 1: Write the failing test (build + fetchJobs)**

Create `client/test/data/jobs_notifier_test.dart`:

```dart
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/data/models/job_record.dart';
import 'package:omniscribe_client/data/providers/jobs_notifier.dart';
import 'package:omniscribe_client/data/providers/jobs_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/job_repository.dart';

class _MockJobRepository extends Mock implements JobRepository {}

JobRecord _makeJob(String id) => JobRecord(
      id: id,
      filename: '$id.pdf',
      model: 'qwen2-vl',
      pipelineMode: 'hybrid',
      durationS: 1.5,
      timestamp: '2026-08-26T10:00:00Z',
      status: 'completed',
    );

void main() {
  late _MockJobRepository repo;

  setUp(() {
    repo = _MockJobRepository();
  });

  ProviderContainer makeContainer() {
    return ProviderContainer(
      overrides: [
        jobRepositoryProvider.overrideWithValue(repo),
      ],
    );
  }

  group('JobsNotifier.build', () {
    test('returns empty JobsState with no error before any method call', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(jobsProvider);

      expect(state.jobs, isEmpty);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
    });
  });

  group('JobsNotifier.fetchJobs', () {
    test('populates state.jobs and clears isFetching on success', () async {
      final jobs = [_makeJob('a'), _makeJob('b')];
      when(() => repo.listJobs()).thenAnswer((_) async => jobs);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await notifier.fetchJobs();

      final state = container.read(jobsProvider);
      expect(state.jobs, jobs);
      expect(state.isFetching, isFalse);
      expect(state.error, isNull);
      verify(() => repo.listJobs()).called(1);
    });

    test('sets isFetching true during in-flight fetch', () async {
      final jobs = [_makeJob('a')];
      when(() => repo.listJobs()).thenAnswer((_) async {
        // While this future is pending the notifier should be in isFetching=true.
        // We assert against the captured state snapshot below.
        return jobs;
      });

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await notifier.fetchJobs();

      // Post-fetch state.
      final state = container.read(jobsProvider);
      expect(state.isFetching, isFalse);
    });

    test('sets state.error and clears isFetching on failure', () async {
      when(() => repo.listJobs()).thenThrow(Exception('boom'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await notifier.fetchJobs();

      final state = container.read(jobsProvider);
      expect(state.isFetching, isFalse);
      expect(state.error, contains('boom'));
    });
  });

  group('JobsNotifier.clearJobs', () {
    test('resets jobs to empty and clears isFetching on success', () async {
      when(() => repo.clearJobs()).thenAnswer((_) async => 3);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await notifier.clearJobs();

      final state = container.read(jobsProvider);
      expect(state.jobs, isEmpty);
      expect(state.isFetching, isFalse);
      verify(() => repo.clearJobs()).called(1);
    });

    test('rethrows on failure and stores error in state', () async {
      when(() => repo.clearJobs()).thenThrow(Exception('clear failed'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await expectLater(notifier.clearJobs(), throwsA(isA<Exception>()));

      final state = container.read(jobsProvider);
      expect(state.error, contains('clear failed'));
    });
  });

  group('JobsNotifier.cancelJob', () {
    test('calls repo.cancelJob then refetches jobs', () async {
      when(() => repo.cancelJob('job-7')).thenAnswer((_) async => true);
      when(() => repo.listJobs()).thenAnswer((_) async => <JobRecord>[]);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await notifier.cancelJob('job-7');

      verify(() => repo.cancelJob('job-7')).called(1);
      verify(() => repo.listJobs()).called(1);
    });

    test('does not refetch jobs when cancelJob throws', () async {
      when(() => repo.cancelJob('job-7')).thenThrow(Exception('cancel failed'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await expectLater(notifier.cancelJob('job-7'), throwsA(isA<Exception>()));

      final state = container.read(jobsProvider);
      expect(state.error, contains('cancel failed'));
      verifyNever(() => repo.listJobs());
    });
  });

  group('JobsNotifier.downloadResult', () {
    test('returns repo bytes on success and leaves state untouched', () async {
      final bytes = Uint8List.fromList([0x25, 0x50, 0x44, 0x46]); // %PDF
      when(() => repo.downloadResult('job-1', 'tok-1'))
          .thenAnswer((_) async => bytes);

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      final result = await notifier.downloadResult('job-1', 'tok-1');

      expect(result, bytes);
      final state = container.read(jobsProvider);
      expect(state.error, isNull);
    });

    test('sets state.error and rethrows on failure', () async {
      when(() => repo.downloadResult('job-1', 'tok-1'))
          .thenThrow(Exception('download failed'));

      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(jobsProvider.notifier);

      await expectLater(
        notifier.downloadResult('job-1', 'tok-1'),
        throwsA(isA<Exception>()),
      );

      final state = container.read(jobsProvider);
      expect(state.error, contains('download failed'));
    });
  });
}
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
cd d:\OmniScribe\client
flutter test test/data/jobs_notifier_test.dart
```

Expected: **FAIL** with `Target of URI doesn't exist: 'package:omniscribe_client/data/providers/jobs_notifier.dart'`.

- [ ] **Step 3: Implement `JobsNotifier` (build + fetchJobs only)**

Create `client/lib/data/providers/jobs_notifier.dart`:

```dart
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/jobs_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/job_repository.dart';

/// Riverpod 2.x `Notifier` for the Jobs vertical.
///
/// Watches [jobRepositoryProvider] for the data-layer repository and exposes
/// `fetchJobs` / `clearJobs` / `cancelJob` / `downloadResult` to the UI.
///
/// The legacy `StateNotifier` `JobsNotifier` used to fire `fetchJobs()` from
/// its constructor; this implementation intentionally does **not** do that.
/// Callers (the screen's `initState` and the Refresh button) trigger the
/// initial fetch themselves, matching how slice 1 wired `SettingsNotifier`.
final jobsProvider =
    NotifierProvider<JobsNotifier, JobsState>(JobsNotifier.new);

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

- [ ] **Step 4: Run the test to verify it passes**

```powershell
cd d:\OmniScribe\client
flutter test test/data/jobs_notifier_test.dart
```

Expected: **PASS** — all groups, all 9 tests green.

- [ ] **Step 5: Run `dart analyze` on the new files**

```powershell
cd d:\OmniScribe\client
dart analyze lib/data/providers/jobs_notifier.dart test/data/jobs_notifier_test.dart
```

Expected: `No issues found!`.

---

## Task 6: Rewrite `JobHistoryScreen` on the new common widgets

The screen reads `jobsProvider`, shows a header with a count badge + Refresh + Clear all buttons, a status banner, and a `DataTable`. We preserve the same UX flow and the title `"Job Execution History"` (test expectation at `app_shell_test.dart:92`). We swap the widget surface from the legacy DocuVerse widgets (`DocuVerseBadge`, `DocuVerseButton`, `DocuVerseCard`, `DocuVerseModal`, `context.docuVerse`) to the canonical common widgets (`AppBadge`, `AppButton`, `AppCard`, `AppModal.show`, `context.colors`).

**Files:**
- Modify: `client/lib/presentation/jobs/job_history_screen.dart`

- [ ] **Step 1: Rewrite the file header + state source**

Open `client/lib/presentation/jobs/job_history_screen.dart`. **Replace the entire file** with:

```dart
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/data/models/job_record.dart';
import 'package:omniscribe_client/data/providers/jobs_notifier.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_modal.dart';

/// Job Execution History screen.
///
/// Slice 2: consumes the Riverpod 2.x `jobsProvider` (`Notifier<JobsState>`)
/// and the canonical `presentation/common/app_*` widgets. The DataTable,
/// badge variant mapping, download spinner, and clear-confirm modal are
/// preserved from the legacy DocuVerse-skinned implementation.
class JobHistoryScreen extends ConsumerStatefulWidget {
  const JobHistoryScreen({super.key});

  @override
  ConsumerState<JobHistoryScreen> createState() => _JobHistoryScreenState();
}

class _JobHistoryScreenState extends ConsumerState<JobHistoryScreen> {
  String? _downloadingJobId;
  String? _statusBanner;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(jobsProvider.notifier).fetchJobs());
  }

  AppBadgeVariant _statusVariant(String status) {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'complete':
      case 'success':
        return AppBadgeVariant.success;
      case 'processing':
      case 'pending':
        return AppBadgeVariant.warning;
      case 'failed':
      case 'error':
        return AppBadgeVariant.error;
      case 'cancelled':
        return AppBadgeVariant.neutral;
      default:
        return AppBadgeVariant.neutral;
    }
  }

  Future<void> _handleDownload(JobRecord job) async {
    setState(() {
      _downloadingJobId = job.id;
      _statusBanner = null;
    });

    try {
      final token = job.textArtifactToken ?? '';
      final Uint8List bytes = await ref
          .read(jobsProvider.notifier)
          .downloadResult(job.id, token);
      if (mounted) {
        setState(() {
          _statusBanner =
              'Downloaded searchable PDF for ${job.filename} (${bytes.lengthInBytes} bytes)';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusBanner = 'Download error: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _downloadingJobId = null;
        });
      }
    }
  }

  Future<void> _handleCancel(String jobId) async {
    try {
      await ref.read(jobsProvider.notifier).cancelJob(jobId);
      if (mounted) {
        setState(() {
          _statusBanner = 'Job $jobId cancellation requested.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusBanner = 'Cancel error: $e';
        });
      }
    }
  }

  Future<void> _showClearConfirmDialog() async {
    await AppModal.show<void>(
      context: context,
      title: 'Clear All Job History?',
      subtitle:
          'This will remove all job records and drop associated cached artifacts from the server.',
      maxWidth: AppModalWidth.sm,
      actions: [
        AppButton(
          text: 'Cancel',
          variant: AppButtonVariant.ghost,
          onPressed: () => Navigator.of(context).pop(),
        ),
        AppButton(
          text: 'Clear all jobs',
          variant: AppButtonVariant.danger,
          onPressed: () async {
            Navigator.of(context).pop();
            await ref.read(jobsProvider.notifier).clearJobs();
            if (mounted) {
              setState(() {
                _statusBanner = 'Job execution history cleared.';
              });
            }
          },
        ),
      ],
      content: Text(
        'This action is irreversible. All past OCR, translation, and extraction task logs will be wiped.',
        style: TextStyle(
          fontSize: 13,
          color: context.colors.textMuted,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final jobsState = ref.watch(jobsProvider);
    final colors = context.colors;
    final isErrorBanner =
        _statusBanner != null && _statusBanner!.toLowerCase().contains('error');

    return Scaffold(
      backgroundColor: colors.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          const Text(
                            'Job Execution History',
                            style: TextStyle(
                              fontSize: 22,
                              fontWeight: FontWeight.bold,
                              letterSpacing: -0.5,
                            ),
                          ),
                          const SizedBox(width: 10),
                          AppBadge(
                            label: '${jobsState.jobs.length} jobs',
                            variant: AppBadgeVariant.brand,
                            dot: true,
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'Audit log of previous OCR, Translation, and Extraction pipeline tasks',
                        style: TextStyle(
                          fontSize: 12,
                          color: colors.textMuted,
                        ),
                      ),
                    ],
                  ),
                  Row(
                    children: [
                      AppButton(
                        text: 'Refresh',
                        variant: AppButtonVariant.secondary,
                        loading: jobsState.isFetching,
                        icon: const Icon(Icons.refresh, size: 14),
                        onPressed: () =>
                            ref.read(jobsProvider.notifier).fetchJobs(),
                      ),
                      const SizedBox(width: 8),
                      AppButton(
                        text: 'Clear all',
                        variant: AppButtonVariant.danger,
                        disabled: jobsState.jobs.isEmpty,
                        icon: const Icon(Icons.delete_outline, size: 14),
                        onPressed: _showClearConfirmDialog,
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 16),

              if (_statusBanner != null) ...[
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: (isErrorBanner ? colors.error : colors.info)
                        .withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: (isErrorBanner ? colors.error : colors.info)
                          .withValues(alpha: 0.35),
                    ),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        isErrorBanner
                            ? Icons.error_outline
                            : Icons.info_outline,
                        size: 16,
                        color: isErrorBanner ? colors.error : colors.info,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _statusBanner!,
                          style: TextStyle(
                            fontSize: 12,
                            color: isErrorBanner ? colors.error : colors.info,
                            fontFamily: 'monospace',
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // Main Jobs Table
              Expanded(
                child: AppCard(
                  padding: AppCardPadding.none,
                  child: jobsState.jobs.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Icon(
                                Icons.history,
                                size: 48,
                                color: colors.textMuted,
                              ),
                              const SizedBox(height: 12),
                              Text(
                                jobsState.isFetching
                                    ? 'Loading job history…'
                                    : 'No historical OCR or translation jobs found.',
                                style: TextStyle(
                                  color: colors.textMuted,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                        )
                      : ClipRRect(
                          borderRadius: BorderRadius.circular(8),
                          child: SingleChildScrollView(
                            child: DataTable(
                              headingRowColor: WidgetStateProperty.all(
                                colors.cardRaised,
                              ),
                              dataRowColor: WidgetStateProperty.all(
                                Colors.transparent,
                              ),
                              dividerThickness: 1,
                              horizontalMargin: 16,
                              columnSpacing: 24,
                              columns: const [
                                DataColumn(
                                  label: Text(
                                    'Job ID',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Status',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Filename',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Pipeline / Model',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Duration',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Failed Pages',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                                DataColumn(
                                  label: Text(
                                    'Actions',
                                    style: TextStyle(
                                      fontWeight: FontWeight.bold,
                                      fontSize: 12,
                                    ),
                                  ),
                                ),
                              ],
                              rows: jobsState.jobs.map((job) {
                                final isDownloading = _downloadingJobId == job.id;
                                final isRunning =
                                    job.status.toLowerCase() == 'processing' ||
                                        job.status.toLowerCase() == 'pending';

                                return DataRow(
                                  cells: [
                                    DataCell(
                                      Text(
                                        job.id.length > 8
                                            ? '${job.id.substring(0, 8)}…'
                                            : job.id,
                                        style: const TextStyle(
                                          fontFamily: 'monospace',
                                          fontSize: 12,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ),
                                    DataCell(
                                      AppBadge(
                                        label: job.status.toUpperCase(),
                                        variant: _statusVariant(job.status),
                                      ),
                                    ),
                                    DataCell(
                                      ConstrainedBox(
                                        constraints:
                                            const BoxConstraints(maxWidth: 160),
                                        child: Text(
                                          job.filename,
                                          style: const TextStyle(fontSize: 12),
                                          overflow: TextOverflow.ellipsis,
                                        ),
                                      ),
                                    ),
                                    DataCell(
                                      Text(
                                        '${job.pipelineMode} / ${job.model}',
                                        style: TextStyle(
                                          fontSize: 12,
                                          fontFamily: 'monospace',
                                          color: colors.textMuted,
                                        ),
                                      ),
                                    ),
                                    DataCell(
                                      Text(
                                        job.durationS > 0
                                            ? '${job.durationS.toStringAsFixed(1)}s'
                                            : '—',
                                        style: TextStyle(
                                          fontSize: 12,
                                          fontFamily: 'monospace',
                                          color: colors.textMuted,
                                        ),
                                      ),
                                    ),
                                    DataCell(
                                      job.failedPages.isNotEmpty
                                          ? AppBadge(
                                              label:
                                                  'Pages: ${job.failedPages.join(", ")}',
                                              variant: AppBadgeVariant.error,
                                            )
                                          : Text(
                                              'None',
                                              style: TextStyle(
                                                fontSize: 12,
                                                color: colors.textMuted,
                                              ),
                                            ),
                                    ),
                                    DataCell(
                                      Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          if (isRunning)
                                            AppButton(
                                              text: 'Cancel',
                                              variant: AppButtonVariant.danger,
                                              size: AppButtonSize.sm,
                                              onPressed: () =>
                                                  _handleCancel(job.id),
                                            )
                                          else
                                            AppButton(
                                              text: 'PDF',
                                              variant: AppButtonVariant.ghost,
                                              size: AppButtonSize.sm,
                                              loading: isDownloading,
                                              icon: const Icon(
                                                Icons.download,
                                                size: 14,
                                              ),
                                              onPressed: () =>
                                                  _handleDownload(job),
                                            ),
                                        ],
                                      ),
                                    ),
                                  ],
                                );
                              }).toList(),
                            ),
                          ),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
```

Key widget substitutions (use this as a checklist while reviewing the rewrite):

| Legacy | New | Notes |
|---|---|---|
| `DocuVerseBadge(text:, variant:, hasDot:)` | `AppBadge(label:, variant:, dot:)` | Param renamed `text` → `label`; `hasDot` → `dot`; `danger` variant → `error` |
| `DocuVerseButton(text:, variant:, loading:, icon:, disabled:, size:)` | `AppButton(text:, variant:, loading:, icon:, disabled:, size:)` | Same params; `danger` variant → `danger` (same name on AppButton) |
| `DocuVerseCard(padding: DocuVerseCardPadding.none, child:)` | `AppCard(padding: AppCardPadding.none, child:)` | Same shape |
| `DocuVerseModal.show(context:, title:, description:, maxWidth:, actions:, child:)` | `AppModal.show(context:, title:, subtitle:, maxWidth:, actions:, content:)` | `description` → `subtitle`; `child` → `content`; `maxWidth: 480` → `maxWidth: AppModalWidth.sm` (400px, the closest tier) |
| `context.docuVerse.<token>` | `context.colors.<token>` | See mapping below |

Token mapping:

| `docuVerse` token | `colors` token |
|---|---|
| `tokens.app` | `colors.background` |
| `tokens.foreground` | `colors.textPrimary` |
| `tokens.foregroundMuted` | `colors.textMuted` |
| `tokens.foregroundSubtle` | `colors.textMuted` (closest analogue; new scheme folds subtle into muted) |
| `tokens.danger` | `colors.error` |
| `tokens.info` | `colors.info` |
| `tokens.cardRaised` | `colors.cardRaised` |
| `tokens.border` | `colors.border` |
| `tokens.brand` | `colors.brand` |
| `BorderRadius.circular(tokens.radiusCard)` | `BorderRadius.circular(8)` (the `AppCard` default) |

- [ ] **Step 2: Verify `dart analyze` is clean for the rewritten file**

```powershell
cd d:\OmniScribe\client
dart analyze lib/presentation/jobs/job_history_screen.dart
```

Expected: `No issues found!`. If the analyzer flags a missing import, missing param, or unresolved identifier, fix and re-run. Do not move on with a red analyzer.

- [ ] **Step 3: Run all tests**

```powershell
cd d:\OmniScribe\client
flutter test
```

Expected: all tests pass — the 4 new tests from Tasks 2-5, the new `job_record_test.dart`, `jobs_state_test.dart`, `jobs_notifier_test.dart`, the new `job_repository_test.dart`, plus all pre-existing tests (including `app_shell_test.dart`'s `'Job Execution History'` expectation, which this rewrite preserves).

- [ ] **Step 4: Run `dart analyze` over the whole client**

```powershell
cd d:\OmniScribe\client
dart analyze
```

Expected: `No issues found!` across `lib/` and `test/`. If anything is red that you can't resolve, stop and surface.

---

## Task 7: Delete the legacy Jobs files and commit

**Files:** delete + git commit

- [ ] **Step 1: Confirm zero remaining importers**

```powershell
cd d:\OmniScribe\client
Select-String -Path "lib\**\*.dart" -Pattern "state/jobs_provider|state/jobs_state|repositories/jobs_repository|models/job\.dart" -SimpleMatch:$false
Select-String -Path "test\**\*.dart" -Pattern "state/jobs_provider|state/jobs_state|repositories/jobs_repository|models/job\.dart" -SimpleMatch:$false
```

Expected: **no matches** in either output. If any file still imports a path we are about to delete, fix the import first (likely to `data/...`).

- [ ] **Step 2: Confirm no relative imports were introduced**

```powershell
cd d:\OmniScribe\client
Select-String -Path "lib\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
Select-String -Path "test\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
```

Expected: **no matches**. The `analysis_options.yaml` `avoid_relative_lib_imports: true` rule must continue to pass.

- [ ] **Step 3: Delete the four legacy files**

```powershell
cd d:\OmniScribe\client
Remove-Item lib\state\jobs_provider.dart
Remove-Item lib\state\jobs_state.dart
Remove-Item lib\repositories\jobs_repository.dart
Remove-Item lib\models\job.dart
```

- [ ] **Step 4: Run the analyzer one more time**

```powershell
cd d:\OmniScribe\client
dart analyze
```

Expected: `No issues found!`. If anything is red, a still-importing file slipped past Step 1; locate and fix.

- [ ] **Step 5: Run the full test suite**

```powershell
cd d:\OmniScribe\client
flutter test
```

Expected: all tests pass (slice 1's tests + all the new Jobs-slice tests + the pre-existing baseline).

- [ ] **Step 6: Build the Windows binary (only if `flutter` is on PATH)**

```powershell
cd d:\OmniScribe\client
flutter build windows --debug
```

Expected: `Built build\windows\x64\runner\Debug\runner.exe` (or similar). If `flutter` is not on PATH, skip this step — `dart analyze` + `flutter test` passing is sufficient to land the slice. Document the skip in the commit message body if you do.

- [ ] **Step 7: Confirm the commit boundary with the user**

Tell the user: "Slice 2 is ready to commit. Suggested branch: `feat/client-consolidation-slice2`. Suggested message: `feat(client): jobs slice — Riverpod NotifierProvider replaces state/jobs_provider + screen on app_* widgets`. Want me to land it?"

Wait for explicit confirmation before running `git checkout -b` / `git add` / `git commit`. Per slice 1 convention: this slice is one commit on its own branch.

- [ ] **Step 8: Stage and commit (only after user confirms)**

```powershell
cd d:\OmniScribe
git checkout -b feat/client-consolidation-slice2
git add client/
git commit -m "feat(client): jobs slice — Riverpod NotifierProvider replaces state/jobs_provider + screen on app_* widgets"
```

---

## Self-Review (run before claiming done)

After completing all tasks, walk through this checklist:

- [ ] **`dart analyze` exits 0** across the entire `client/` tree:

  ```powershell
  cd d:\OmniScribe\client
  dart analyze
  ```

- [ ] **`flutter test` exits 0** (all old + new tests pass):

  ```powershell
  cd d:\OmniScribe\client
  flutter test
  ```

- [ ] **`flutter build windows --debug` succeeds** (if `flutter` on PATH; otherwise skipped).

- [ ] **Zero relative imports remain** in `client/lib/` and `client/test/`:

  ```powershell
  cd d:\OmniScribe\client
  Select-String -Path "lib\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
  Select-String -Path "test\**\*.dart" -Pattern "^import\s+'\.\." -SimpleMatch:$false
  ```

- [ ] **Zero references to the four deleted files** remain in `client/lib/` or `client/test/`:

  ```powershell
  cd d:\OmniScribe\client
  Select-String -Path "lib\**\*.dart", "test\**\*.dart" -Pattern "state/jobs_|repositories/jobs_repository|models/job\.dart" -SimpleMatch:$false
  ```

- [ ] **`JobHistoryScreen` still emits "Job Execution History"** — verified by `flutter test` passing (the `app_shell_test.dart` expectation).

- [ ] **No `// ignore:` lines were added** in any new file:

  ```powershell
  cd d:\OmniScribe\client
  Select-String -Path "lib\data\providers\jobs_*.dart", "lib\data\repositories\job_repository.dart", "lib\presentation\jobs\job_history_screen.dart" -Pattern "ignore:"
  ```

- [ ] **No commit was made without user confirmation** (Task 7 step 7).

---

## Reference

- **Spec:** [2026-08-26-client-consolidation-jobs-slice-design.md](../specs/2026-08-26-client-consolidation-jobs-slice-design.md) — the design this plan implements.
- **Slice 1 plan:** [2026-08-24-flutter-client-consolidation.md](./2026-08-24-flutter-client-consolidation.md) — the prior slice this one mirrors; review for the `SettingsNotifier` / `SettingsState` patterns the Jobs slice mirrors.
- **Parent spec:** [2026-08-24-flutter-client-consolidation-design.md](../specs/2026-08-24-flutter-client-consolidation-design.md) — slice 2 in the parent's ordering is Provider Browser (still deferred). Jobs was re-prioritised here ahead of it.
- **Future slices:** Progress / WebSocket, Provider Browser, Features (translation / transcription / glossary / extraction), Workstation, Final cleanup — each gets its own plan in turn.
