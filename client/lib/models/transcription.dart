/// Voice & audio transcription models.
class TranscriptionSegment {
  const TranscriptionSegment({
    this.id,
    required this.start,
    required this.end,
    required this.text,
  });

  final int? id;
  final double start;
  final double end;
  final String text;

  factory TranscriptionSegment.fromJson(Map<String, dynamic> json) {
    return TranscriptionSegment(
      id: (json['id'] as num?)?.toInt(),
      start: (json['start'] as num?)?.toDouble() ?? 0.0,
      end: (json['end'] as num?)?.toDouble() ?? 0.0,
      text: json['text'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      if (id != null) 'id': id,
      'start': start,
      'end': end,
      'text': text,
    };
  }
}

class TranscriptionJobResponse {
  const TranscriptionJobResponse({
    required this.text,
    this.segments = const [],
    this.filename,
    this.language,
    this.duration,
    this.jobId,
  });

  final String text;
  final List<TranscriptionSegment> segments;
  final String? filename;
  final String? language;
  final double? duration;
  final String? jobId;

  factory TranscriptionJobResponse.fromJson(Map<String, dynamic> json) {
    final rawSegments = json['segments'] as List<dynamic>? ?? const [];
    return TranscriptionJobResponse(
      text: json['text'] as String? ?? '',
      segments: rawSegments
          .map((e) => TranscriptionSegment.fromJson(e as Map<String, dynamic>))
          .toList(),
      filename: json['filename'] as String?,
      language: json['language'] as String?,
      duration: (json['duration'] as num?)?.toDouble(),
      jobId: json['job_id'] as String?,
    );
  }
}
