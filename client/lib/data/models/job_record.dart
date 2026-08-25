/// Job lifecycle, history records, and asynchronous submission models.

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
    };
  }
}

/// Response returned from GET /api/process/status/{job_id}
class OcrJobStatusResponse {
  const OcrJobStatusResponse({
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

  bool get isPending => status == 'pending' || status == 'queued';
  bool get isProcessing => status == 'processing' || status == 'running';
  bool get isComplete => status == 'complete';
  bool get isError => status == 'error' || status == 'cancelled';

  factory OcrJobStatusResponse.fromJson(Map<String, dynamic> json) {
    final failed = <int>[];
    if (json['failed_pages'] is List) {
      for (final item in json['failed_pages'] as List) {
        if (item is num) failed.add(item.toInt());
      }
    }

    return OcrJobStatusResponse(
      jobId: json['job_id']?.toString() ?? '',
      filename: json['filename']?.toString() ?? '',
      status: json['status']?.toString() ?? 'pending',
      createdAt: (json['created_at'] as num?)?.toDouble() ?? 0.0,
      startedAt: (json['started_at'] as num?)?.toDouble(),
      completedAt: (json['completed_at'] as num?)?.toDouble(),
      durationS: (json['duration_s'] as num?)?.toDouble(),
      error: json['error']?.toString(),
      textArtifactId: json['text_artifact_id']?.toString(),
      textArtifactToken: json['text_artifact_token']?.toString(),
      textArtifactUrl: json['text_artifact_url']?.toString(),
      failedPages: failed,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'job_id': jobId,
      'filename': filename,
      'status': status,
      'created_at': createdAt,
      if (startedAt != null) 'started_at': startedAt,
      if (completedAt != null) 'completed_at': completedAt,
      if (durationS != null) 'duration_s': durationS,
      if (error != null) 'error': error,
      if (textArtifactId != null) 'text_artifact_id': textArtifactId,
      if (textArtifactToken != null)
        'text_artifact_token': textArtifactToken,
      if (textArtifactUrl != null) 'text_artifact_url': textArtifactUrl,
      'failed_pages': failedPages,
    };
  }
}

/// Response returned from POST /api/process/async
class ProcessResponse {
  const ProcessResponse({
    required this.jobId,
    required this.status,
    this.statusUrl,
  });

  final String jobId;
  final String status;
  final String? statusUrl;

  factory ProcessResponse.fromJson(Map<String, dynamic> json) {
    return ProcessResponse(
      jobId: json['job_id']?.toString() ?? '',
      status: json['status']?.toString() ?? 'pending',
      statusUrl: json['status_url']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'job_id': jobId,
        'status': status,
        if (statusUrl != null) 'status_url': statusUrl,
      };
}

/// Type alias for async submission response matching backend AsyncSubmitResponse schema.
typedef AsyncSubmitResponse = ProcessResponse;
