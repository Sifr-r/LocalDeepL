/// Translation request and response models.
class TranslationRequest {
  const TranslationRequest({
    this.text,
    this.textArtifactId,
    this.textArtifactToken,
    this.targetLanguage = 'French',
    this.promptTemplate =
        'Translate the following text accurately while maintaining context and terminology.',
    this.model,
    this.apiBase,
    this.apiKey,
    this.slidingWindowWords = 350,
    this.dualTranslate = false,
  });

  final String? text;
  final String? textArtifactId;
  final String? textArtifactToken;
  final String targetLanguage;
  final String promptTemplate;
  final String? model;
  final String? apiBase;
  final String? apiKey;
  final int slidingWindowWords;
  final bool dualTranslate;

  Map<String, dynamic> toJson() {
    return {
      if (text != null) 'text': text,
      if (textArtifactId != null) 'text_artifact_id': textArtifactId,
      if (textArtifactToken != null) 'text_artifact_token': textArtifactToken,
      'target_language': targetLanguage,
      'prompt_template': promptTemplate,
      if (model != null) 'model': model,
      if (apiBase != null) 'api_base': apiBase,
      if (apiKey != null) 'api_key': apiKey,
      'sliding_window_words': slidingWindowWords,
      'dual_translate': dualTranslate,
    };
  }
}

class TranslationResponse {
  const TranslationResponse({
    required this.translatedText,
  });

  final String translatedText;

  factory TranslationResponse.fromJson(Map<String, dynamic> json) {
    return TranslationResponse(
      translatedText: json['translated_text'] as String? ?? '',
    );
  }
}

class NLLBTranslationResponse {
  const NLLBTranslationResponse({
    required this.translatedText,
    this.sourceLang = 'auto',
    this.targetLang = '',
  });

  final String translatedText;
  final String sourceLang;
  final String targetLang;

  factory NLLBTranslationResponse.fromJson(Map<String, dynamic> json) {
    return NLLBTranslationResponse(
      translatedText: json['translated_text'] as String? ?? '',
      sourceLang: json['source_lang'] as String? ?? 'auto',
      targetLang: json['target_lang'] as String? ?? '',
    );
  }
}

class AsyncTranslationResponse {
  const AsyncTranslationResponse({
    required this.jobId,
    required this.status,
  });

  final String jobId;
  final String status;

  factory AsyncTranslationResponse.fromJson(Map<String, dynamic> json) {
    return AsyncTranslationResponse(
      jobId: json['job_id'] as String? ?? '',
      status: json['status'] as String? ?? 'pending',
    );
  }
}

class TranslationJobStatusResponse {
  const TranslationJobStatusResponse({
    required this.jobId,
    required this.state,
    this.status,
    this.result,
    this.error,
    this.detail,
  });

  final String jobId;
  final String state;
  final String? status;
  final dynamic result;
  final String? error;
  final String? detail;

  factory TranslationJobStatusResponse.fromJson(Map<String, dynamic> json) {
    return TranslationJobStatusResponse(
      jobId: json['job_id'] as String? ?? '',
      state: json['state'] as String? ?? json['status'] as String? ?? 'PENDING',
      status: json['status'] as String?,
      result: json['result'],
      error: json['error'] as String?,
      detail: json['detail'] as String?,
    );
  }
}
