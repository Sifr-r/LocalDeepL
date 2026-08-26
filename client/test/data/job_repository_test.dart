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

    test(
        'hits /api/jobs/{jobId}/result with token query param and Bearer header',
        () async {
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
