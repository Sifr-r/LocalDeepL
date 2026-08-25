/// Historical Job Record and OCR status models.
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
    this.failedPages = const [],
    this.textArtifactId,
    this.textArtifactToken,
  });

  final String id;
  final String filename;
  final String model;
  final String pipelineMode;
  final double durationS;
  final String timestamp;
  final String status;
  final String? pages;
  final List<int> failedPages;
  final String? textArtifactId;
  final String? textArtifactToken;

  factory JobRecord.fromJson(Map<String, dynamic> json) {
    return JobRecord(
      id: json['id'] as String? ?? json['job_id'] as String? ?? '',
      filename: json['filename'] as String? ?? 'Document',
      model: json['model'] as String? ?? 'default',
      pipelineMode: json['pipeline_mode'] as String? ?? 'hybrid',
      durationS: (json['duration_s'] as num?)?.toDouble() ?? 0.0,
      timestamp: json['timestamp'] as String? ?? json['created_at']?.toString() ?? '',
      status: json['status'] as String? ?? 'completed',
      pages: json['pages'] as String?,
      failedPages: (json['failed_pages'] as List<dynamic>?)
              ?.map((e) => (e as num).toInt())
              .toList() ??
          const [],
      textArtifactId: json['text_artifact_id'] as String?,
      textArtifactToken: json['text_artifact_token'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'filename': filename,
      'model': model,
      'pipeline_mode': pipelineMode,
      'duration_s': durationS,
      'timestamp': timestamp,
      'status': status,
      if (pages != null) 'pages': pages,
      'failed_pages': failedPages,
      if (textArtifactId != null) 'text_artifact_id': textArtifactId,
      if (textArtifactToken != null) 'text_artifact_token': textArtifactToken,
    };
  }
}

class OcrJobStatus {
  const OcrJobStatus({
    required this.jobId,
    required this.filename,
    required this.status,
    required this.createdAt,
    this.startedAt,
    this.completedAt,
    this.durationS,
    this.error,
    this.textArtifactId,
    this.textArtifactToken,
    this.textArtifactUrl,
    this.failedPages = const [],
  });

  final String jobId;
  final String filename;
  final String status;
  final double createdAt;
  final double? startedAt;
  final double? completedAt;
  final double? durationS;
  final String? error;
  final String? textArtifactId;
  final String? textArtifactToken;
  final String? textArtifactUrl;
  final List<int> failedPages;

  factory OcrJobStatus.fromJson(Map<String, dynamic> json) {
    return OcrJobStatus(
      jobId: json['job_id'] as String? ?? '',
      filename: json['filename'] as String? ?? '',
      status: json['status'] as String? ?? 'pending',
      createdAt: (json['created_at'] as num?)?.toDouble() ?? 0.0,
      startedAt: (json['started_at'] as num?)?.toDouble(),
      completedAt: (json['completed_at'] as num?)?.toDouble(),
      durationS: (json['duration_s'] as num?)?.toDouble(),
      error: json['error'] as String?,
      textArtifactId: json['text_artifact_id'] as String?,
      textArtifactToken: json['text_artifact_token'] as String?,
      textArtifactUrl: json['text_artifact_url'] as String?,
      failedPages: (json['failed_pages'] as List<dynamic>?)
              ?.map((e) => (e as num).toInt())
              .toList() ??
          const [],
    );
  }
}
