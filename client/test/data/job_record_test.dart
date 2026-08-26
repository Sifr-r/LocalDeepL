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
