import 'dart:typed_data';
import 'package:omniscribe_client/models/job.dart';
import 'package:omniscribe_client/services/api_client.dart';

class JobsRepository {
  JobsRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<List<JobRecord>> getJobs() async {
    final res = await _apiClient.get('/jobs');
    if (res is List) {
      return res
          .whereType<Map<String, dynamic>>()
          .map((e) => JobRecord.fromJson(e))
          .toList();
    }
    return const [];
  }

  Future<void> clearJobs() async {
    await _apiClient.delete('/jobs');
  }

  Future<void> cancelJob(String jobId) async {
    await _apiClient.post('/jobs/$jobId/cancel');
  }

  Future<OcrJobStatus> getJobStatus(String jobId) async {
    final res = await _apiClient.get('/process/status/$jobId');
    if (res is Map<String, dynamic>) {
      return OcrJobStatus.fromJson(res);
    }
    throw ApiException('Failed to parse job status');
  }

  Future<Uint8List> downloadResult(String jobId, String token) async {
    final headers = <String, String>{};
    if (token.isNotEmpty) {
      headers['Authorization'] = 'Bearer $token';
    }
    return _apiClient.getBytes(
      '/jobs/$jobId/result',
      queryParams: {'token': token},
      headers: headers,
    );
  }
}
