import 'dart:typed_data';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/models/job.dart';
import 'package:omniscribe_client/repositories/jobs_repository.dart';
import 'package:omniscribe_client/services/api_client.dart';
import 'jobs_state.dart';

final jobsRepositoryProvider = Provider<JobsRepository>((ref) {
  return JobsRepository(ApiClient());
});

final jobsProvider = StateNotifierProvider<JobsNotifier, JobsState>((ref) {
  final repository = ref.watch(jobsRepositoryProvider);
  return JobsNotifier(repository);
});

class JobsNotifier extends StateNotifier<JobsState> {
  JobsNotifier(this._repository) : super(const JobsState()) {
    fetchJobs();
  }

  final JobsRepository _repository;

  Future<void> fetchJobs() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final jobs = await _repository.getJobs();
      state = state.copyWith(jobs: jobs, isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  Future<void> clearJobs() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      await _repository.clearJobs();
      state = state.copyWith(jobs: const [], isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> cancelJob(String jobId) async {
    try {
      await _repository.cancelJob(jobId);
      await fetchJobs();
    } catch (e) {
      state = state.copyWith(error: e.toString());
      rethrow;
    }
  }

  Future<Uint8List> downloadResult(String jobId, String token) async {
    try {
      return await _repository.downloadResult(jobId, token);
    } catch (e) {
      state = state.copyWith(error: e.toString());
      rethrow;
    }
  }
}
