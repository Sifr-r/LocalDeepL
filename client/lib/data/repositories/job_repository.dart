import 'package:omniscribe_client/core/constants/api_constants.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/data/models/job_record.dart';

abstract class JobRepository {
  /// Retrieve list of all past and current OCR jobs.
  Future<List<JobRecord>> listJobs();

  /// Clear all completed and failed jobs from queue/history.
  Future<int> clearJobs();

  /// Cancel a running or queued job by ID.
  Future<bool> cancelJob(String jobId);
}

class JobRepositoryImpl implements JobRepository {
  const JobRepositoryImpl(this._apiClient);

  final ApiClient _apiClient;

  @override
  Future<List<JobRecord>> listJobs() async {
    final dynamic response = await _apiClient.get<dynamic>(
      ApiConstants.jobs,
    );

    final list = <JobRecord>[];
    if (response is List) {
      for (final item in response) {
        if (item is Map<String, dynamic>) {
          list.add(JobRecord.fromJson(item));
        }
      }
    }
    return list;
  }

  @override
  Future<int> clearJobs() async {
    final json = await _apiClient.delete<Map<String, dynamic>>(
      ApiConstants.jobs,
    );
    return (json['cleared'] as num?)?.toInt() ?? 0;
  }

  @override
  Future<bool> cancelJob(String jobId) async {
    final json = await _apiClient.post<Map<String, dynamic>>(
      ApiConstants.cancelJob(jobId),
    );
    return json['cancelled'] as bool? ?? false;
  }
}
