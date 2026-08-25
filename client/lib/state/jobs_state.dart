import 'package:omniscribe_client/models/job.dart';

class JobsState {
  const JobsState({
    this.jobs = const [],
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
