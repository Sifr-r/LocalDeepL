/// Domain models for OmniScribe features: Translation, Transcription, Structured Extraction, Glossary, and Document Export.
library;

/// Structured information extraction templates.
enum ExtractionTemplate {
  invoice('invoice'),
  resume('resume'),
  academic('academic'),
  table('table'),
  tableExtraction('table_extraction'),
  custom('custom');

  const ExtractionTemplate(this.value);
  final String value;

  static ExtractionTemplate fromString(String? value) {
    if (value == null) return ExtractionTemplate.custom;
    for (final t in ExtractionTemplate.values) {
      if (t.value == value) return t;
    }
    return ExtractionTemplate.custom;
  }
}

/// Supported structured document export formats.
enum DocumentExportFormat {
  json('json'),
  markdown('markdown'),
  text('text'),
  docling('docling'),
  mineru('mineru');

  const DocumentExportFormat(this.value);
  final String value;

  static DocumentExportFormat fromString(String? value) {
    if (value == null) return DocumentExportFormat.markdown;
    for (final f in DocumentExportFormat.values) {
      if (f.value == value) return f;
    }
    return DocumentExportFormat.markdown;
  }
}

/// Glossary storage and file formats.
enum GlossaryFormat {
  csv('csv'),
  tsv('tsv'),
  xliff('xliff'),
  tbx('tbx'),
  tmx('tmx'),
  gitGlossary('git_glossary'),
  sqlTable('sql_table'),
  jsonPairs('json_pairs');

  const GlossaryFormat(this.value);
  final String value;

  static GlossaryFormat fromString(String? value) {
    if (value == null) return GlossaryFormat.csv;
    for (final f in GlossaryFormat.values) {
      if (f.value == value) return f;
    }
    return GlossaryFormat.csv;
  }
}

/// Audio transcription engine types.
enum TranscriptionEngineType {
  api('api'),
  whisperApi('whisper_api'),
  local('local'),
  whisperLocal('whisper_local'),
  auto('auto');

  const TranscriptionEngineType(this.value);
  final String value;

  static TranscriptionEngineType fromString(String? value) {
    if (value == null) return TranscriptionEngineType.auto;
    for (final e in TranscriptionEngineType.values) {
      if (e.value == value) return e;
    }
    return TranscriptionEngineType.auto;
  }
}

// ---------------------------------------------------------------------------
// Translation Models
// ---------------------------------------------------------------------------

class TranslationRequest {
  const TranslationRequest({
    this.text,
    this.textArtifactId,
    this.textArtifactToken,
    this.promptTemplate,
    this.targetLanguage = 'English',
    this.apiBase,
    this.apiKey,
    this.model,
    this.glossary,
    this.glossaryText,
    this.slidingWindowWords,
    this.dualTranslate,
    this.secondApiBase,
    this.secondApiKey,
    this.secondModel,
    this.channelId,
  });

  final String? text;
  final String? textArtifactId;
  final String? textArtifactToken;
  final String? promptTemplate;
  final String? targetLanguage;
  final String? apiBase;
  final String? apiKey;
  final String? model;
  final List<Map<String, dynamic>>? glossary;
  final String? glossaryText;
  final int? slidingWindowWords;
  final bool? dualTranslate;
  final String? secondApiBase;
  final String? secondApiKey;
  final String? secondModel;
  final String? channelId;

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{};
    void addIfNonNull(String k, dynamic v) {
      if (v != null) map[k] = v;
    }

    addIfNonNull('text', text);
    addIfNonNull('text_artifact_id', textArtifactId);
    addIfNonNull('text_artifact_token', textArtifactToken);
    addIfNonNull('prompt_template', promptTemplate);
    addIfNonNull('target_language', targetLanguage);
    addIfNonNull('api_base', apiBase);
    addIfNonNull('api_key', apiKey);
    addIfNonNull('model', model);
    addIfNonNull('glossary', glossary);
    addIfNonNull('glossary_text', glossaryText);
    addIfNonNull('sliding_window_words', slidingWindowWords);
    addIfNonNull('dual_translate', dualTranslate);
    addIfNonNull('second_api_base', secondApiBase);
    addIfNonNull('second_api_key', secondApiKey);
    addIfNonNull('second_model', secondModel);
    addIfNonNull('channel_id', channelId);
    return map;
  }

  factory TranslationRequest.fromJson(Map<String, dynamic> json) {
    List<Map<String, dynamic>>? glossList;
    if (json['glossary'] is List) {
      glossList =
          (json['glossary'] as List).whereType<Map<String, dynamic>>().toList();
    }

    return TranslationRequest(
      text: json['text']?.toString(),
      textArtifactId: json['text_artifact_id']?.toString(),
      textArtifactToken: json['text_artifact_token']?.toString(),
      promptTemplate: json['prompt_template']?.toString(),
      targetLanguage: json['target_language']?.toString(),
      apiBase: json['api_base']?.toString(),
      apiKey: json['api_key']?.toString(),
      model: json['model']?.toString(),
      glossary: glossList,
      glossaryText: json['glossary_text']?.toString(),
      slidingWindowWords: (json['sliding_window_words'] as num?)?.toInt(),
      dualTranslate: json['dual_translate'] as bool?,
      secondApiBase: json['second_api_base']?.toString(),
      secondApiKey: json['second_api_key']?.toString(),
      secondModel: json['second_model']?.toString(),
      channelId: json['channel_id']?.toString(),
    );
  }
}

class TranslationResponse {
  const TranslationResponse({required this.translatedText});

  final String translatedText;

  factory TranslationResponse.fromJson(Map<String, dynamic> json) {
    return TranslationResponse(
      translatedText: json['translated_text']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() => {'translated_text': translatedText};
}

class NLLBTranslationResponse {
  const NLLBTranslationResponse({
    required this.translatedText,
    required this.sourceLang,
    required this.targetLang,
  });

  final String translatedText;
  final String sourceLang;
  final String targetLang;

  factory NLLBTranslationResponse.fromJson(Map<String, dynamic> json) {
    return NLLBTranslationResponse(
      translatedText: json['translated_text']?.toString() ?? '',
      sourceLang: json['source_lang']?.toString() ?? '',
      targetLang: json['target_lang']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() => {
        'translated_text': translatedText,
        'source_lang': sourceLang,
        'target_lang': targetLang,
      };
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
      jobId: json['job_id']?.toString() ?? '',
      state: json['state']?.toString() ?? json['status']?.toString() ?? 'PENDING',
      status: json['status']?.toString(),
      result: json['result'],
      error: json['error']?.toString(),
      detail: json['detail']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'job_id': jobId,
        'state': state,
        if (status != null) 'status': status,
        if (result != null) 'result': result,
        if (error != null) 'error': error,
        if (detail != null) 'detail': detail,
      };
}


// ---------------------------------------------------------------------------
// Transcription Models
// ---------------------------------------------------------------------------

class TranscriptionRequest {
  const TranscriptionRequest({
    this.model,
    this.engine = TranscriptionEngineType.auto,
    this.apiBase,
    this.apiKey,
    this.language,
    this.prompt,
    this.temperature = 0.0,
    this.translateTo,
    this.channelId,
  });

  final String? model;
  final TranscriptionEngineType? engine;
  final String? apiBase;
  final String? apiKey;
  final String? language;
  final String? prompt;
  final double? temperature;
  final String? translateTo;
  final String? channelId;

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{};
    void addIfNonNull(String k, dynamic v) {
      if (v != null) map[k] = v;
    }

    addIfNonNull('model', model);
    if (engine != null) addIfNonNull('engine', engine!.value);
    addIfNonNull('api_base', apiBase);
    addIfNonNull('api_key', apiKey);
    addIfNonNull('language', language);
    addIfNonNull('prompt', prompt);
    addIfNonNull('temperature', temperature);
    addIfNonNull('translate_to', translateTo);
    addIfNonNull('channel_id', channelId);
    return map;
  }

  factory TranscriptionRequest.fromJson(Map<String, dynamic> json) {
    return TranscriptionRequest(
      model: json['model']?.toString(),
      engine: TranscriptionEngineType.fromString(json['engine']?.toString()),
      apiBase: json['api_base']?.toString(),
      apiKey: json['api_key']?.toString(),
      language: json['language']?.toString(),
      prompt: json['prompt']?.toString(),
      temperature: (json['temperature'] as num?)?.toDouble(),
      translateTo: json['translate_to']?.toString(),
      channelId: json['channel_id']?.toString(),
    );
  }
}

class TranscriptionSegment {
  const TranscriptionSegment({
    required this.start,
    required this.end,
    required this.text,
    this.id,
    this.extra = const {},
  });

  final int? id;
  final double start;
  final double end;
  final String text;
  final Map<String, dynamic> extra;

  factory TranscriptionSegment.fromJson(Map<String, dynamic> json) {
    return TranscriptionSegment(
      id: (json['id'] as num?)?.toInt(),
      start: (json['start'] as num?)?.toDouble() ?? 0.0,
      end: (json['end'] as num?)?.toDouble() ?? 0.0,
      text: json['text']?.toString() ?? '',
      extra: json,
    );
  }

  Map<String, dynamic> toJson() => {
        if (id != null) 'id': id,
        'start': start,
        'end': end,
        'text': text,
      };
}

class TranscriptionResponse {
  const TranscriptionResponse({
    required this.text,
    this.segments = const [],
    this.filename,
    this.duration,
    this.textArtifactId,
    this.textArtifactToken,
  });

  final String text;
  final List<TranscriptionSegment> segments;
  final String? filename;
  final double? duration;
  final String? textArtifactId;
  final String? textArtifactToken;

  factory TranscriptionResponse.fromJson(Map<String, dynamic> json) {
    final segs = <TranscriptionSegment>[];
    if (json['segments'] is List) {
      for (final item in json['segments'] as List) {
        if (item is Map<String, dynamic>) {
          segs.add(TranscriptionSegment.fromJson(item));
        }
      }
    }

    return TranscriptionResponse(
      text: json['text']?.toString() ?? '',
      segments: segs,
      filename: json['filename']?.toString(),
      duration: (json['duration'] as num?)?.toDouble(),
      textArtifactId: json['text_artifact_id']?.toString(),
      textArtifactToken: json['text_artifact_token']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'text': text,
        'segments': segments.map((s) => s.toJson()).toList(),
        if (filename != null) 'filename': filename,
        if (duration != null) 'duration': duration,
        if (textArtifactId != null) 'text_artifact_id': textArtifactId,
        if (textArtifactToken != null) 'text_artifact_token': textArtifactToken,
      };
}

// ---------------------------------------------------------------------------
// Extraction Models
// ---------------------------------------------------------------------------

class ExtractionRequest {
  const ExtractionRequest({
    this.text,
    this.template = ExtractionTemplate.custom,
    this.customPrompt,
    this.apiBase,
    this.apiKey,
    this.model,
  });

  final String? text;
  final ExtractionTemplate? template;
  final String? customPrompt;
  final String? apiBase;
  final String? apiKey;
  final String? model;

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{};
    void addIfNonNull(String k, dynamic v) {
      if (v != null) map[k] = v;
    }

    addIfNonNull('text', text);
    if (template != null) addIfNonNull('template', template!.value);
    addIfNonNull('custom_prompt', customPrompt);
    addIfNonNull('api_base', apiBase);
    addIfNonNull('api_key', apiKey);
    addIfNonNull('model', model);
    return map;
  }

  factory ExtractionRequest.fromJson(Map<String, dynamic> json) {
    return ExtractionRequest(
      text: json['text']?.toString(),
      template: ExtractionTemplate.fromString(json['template']?.toString()),
      customPrompt: json['custom_prompt']?.toString(),
      apiBase: json['api_base']?.toString(),
      apiKey: json['api_key']?.toString(),
      model: json['model']?.toString(),
    );
  }
}

class ExtractionResponse {
  const ExtractionResponse({required this.extractedData});

  final dynamic extractedData;

  factory ExtractionResponse.fromJson(Map<String, dynamic> json) {
    return ExtractionResponse(
      extractedData: json['extracted_data'] ?? json,
    );
  }

  Map<String, dynamic> toJson() => {'extracted_data': extractedData};
}

// ---------------------------------------------------------------------------
// Glossary Models
// ---------------------------------------------------------------------------

class GlossaryEntry {
  const GlossaryEntry({
    required this.source,
    required this.target,
    this.note,
    this.extra = const {},
  });

  final String source;
  final String target;
  final String? note;
  final Map<String, dynamic> extra;

  factory GlossaryEntry.fromJson(Map<String, dynamic> json) {
    return GlossaryEntry(
      source: json['source']?.toString() ?? '',
      target: json['target']?.toString() ?? '',
      note: json['note']?.toString(),
      extra: json,
    );
  }

  Map<String, dynamic> toJson() => {
        'source': source,
        'target': target,
        if (note != null) 'note': note,
      };
}

class GlossaryListItem {
  const GlossaryListItem({
    required this.id,
    required this.name,
    required this.format,
    required this.entryCount,
    required this.enabled,
    required this.priority,
    required this.group,
    this.sourceUri,
    this.encoding,
  });

  final String id;
  final String name;
  final GlossaryFormat format;
  final int entryCount;
  final bool enabled;
  final int priority;
  final String group;
  final String? sourceUri;
  final String? encoding;

  factory GlossaryListItem.fromJson(Map<String, dynamic> json) {
    return GlossaryListItem(
      id: json['id']?.toString() ?? '',
      name: json['name']?.toString() ?? '',
      format: GlossaryFormat.fromString(json['format']?.toString()),
      entryCount: (json['entry_count'] as num?)?.toInt() ?? 0,
      enabled: json['enabled'] as bool? ?? true,
      priority: (json['priority'] as num?)?.toInt() ?? 0,
      group: json['group']?.toString() ?? 'default',
      sourceUri: json['source_uri']?.toString(),
      encoding: json['encoding']?.toString(),
    );
  }

  GlossaryListItem copyWith({
    String? id,
    String? name,
    GlossaryFormat? format,
    int? entryCount,
    bool? enabled,
    int? priority,
    String? group,
    String? sourceUri,
    String? encoding,
    bool clearSourceUri = false,
    bool clearEncoding = false,
  }) {
    return GlossaryListItem(
      id: id ?? this.id,
      name: name ?? this.name,
      format: format ?? this.format,
      entryCount: entryCount ?? this.entryCount,
      enabled: enabled ?? this.enabled,
      priority: priority ?? this.priority,
      group: group ?? this.group,
      sourceUri: clearSourceUri ? null : (sourceUri ?? this.sourceUri),
      encoding: clearEncoding ? null : (encoding ?? this.encoding),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'format': format.value,
        'entry_count': entryCount,
        'enabled': enabled,
        'priority': priority,
        'group': group,
        if (sourceUri != null) 'source_uri': sourceUri,
        if (encoding != null) 'encoding': encoding,
      };

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is GlossaryListItem &&
        other.id == id &&
        other.name == name &&
        other.format == format &&
        other.entryCount == entryCount &&
        other.enabled == enabled &&
        other.priority == priority &&
        other.group == group &&
        other.sourceUri == sourceUri &&
        other.encoding == encoding;
  }

  @override
  int get hashCode => Object.hash(
        id,
        name,
        format,
        entryCount,
        enabled,
        priority,
        group,
        sourceUri,
        encoding,
      );
}

class GlossaryPreviewResponse {
  const GlossaryPreviewResponse({
    required this.count,
    this.conflicts = const [],
    this.enabledGlossaries = const [],
  });

  final int count;
  final List<Map<String, dynamic>> conflicts;
  final List<String> enabledGlossaries;

  factory GlossaryPreviewResponse.fromJson(Map<String, dynamic> json) {
    final confs = <Map<String, dynamic>>[];
    if (json['conflicts'] is List) {
      for (final c in json['conflicts'] as List) {
        if (c is Map<String, dynamic>) confs.add(c);
      }
    }
    final gloss = <String>[];
    if (json['enabled_glossaries'] is List) {
      for (final g in json['enabled_glossaries'] as List) {
        if (g != null) gloss.add(g.toString());
      }
    }

    return GlossaryPreviewResponse(
      count: (json['count'] as num?)?.toInt() ?? 0,
      conflicts: confs,
      enabledGlossaries: gloss,
    );
  }

  Map<String, dynamic> toJson() => {
        'count': count,
        'conflicts': conflicts,
        'enabled_glossaries': enabledGlossaries,
      };
}

class GlossaryImportJobResponse {
  const GlossaryImportJobResponse({
    required this.format,
    required this.name,
    required this.entryCount,
    this.glossaryId,
    this.jobId,
    this.warnings = const [],
    this.queued = false,
  });

  final GlossaryFormat format;
  final String name;
  final int entryCount;
  final String? glossaryId;
  final String? jobId;
  final List<String> warnings;
  final bool queued;

  factory GlossaryImportJobResponse.fromJson(Map<String, dynamic> json) {
    final warns = <String>[];
    if (json['warnings'] is List) {
      for (final w in json['warnings'] as List) {
        if (w != null) warns.add(w.toString());
      }
    }

    return GlossaryImportJobResponse(
      format: GlossaryFormat.fromString(json['format']?.toString()),
      name: json['name']?.toString() ?? '',
      entryCount: (json['entry_count'] as num?)?.toInt() ?? 0,
      glossaryId: json['glossary_id']?.toString(),
      jobId: json['job_id']?.toString(),
      warnings: warns,
      queued: json['queued'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'format': format.value,
        'name': name,
        'entry_count': entryCount,
        if (glossaryId != null) 'glossary_id': glossaryId,
        if (jobId != null) 'job_id': jobId,
        'warnings': warnings,
        'queued': queued,
      };
}

// ---------------------------------------------------------------------------
// Document Export Requests & Results
// ---------------------------------------------------------------------------

class DocumentExportRequest {
  const DocumentExportRequest({
    required this.textArtifactId,
    required this.textArtifactToken,
    this.exportFormat = DocumentExportFormat.markdown,
    this.metadataArtifactId,
    this.metadataArtifactToken,
  });

  final String textArtifactId;
  final String textArtifactToken;
  final DocumentExportFormat exportFormat;
  final String? metadataArtifactId;
  final String? metadataArtifactToken;

  Map<String, dynamic> toJson() => {
        'text_artifact_id': textArtifactId,
        'text_artifact_token': textArtifactToken,
        'export_format': exportFormat.value,
        if (metadataArtifactId != null)
          'metadata_artifact_id': metadataArtifactId,
        if (metadataArtifactToken != null)
          'metadata_artifact_token': metadataArtifactToken,
      };

  factory DocumentExportRequest.fromJson(Map<String, dynamic> json) {
    return DocumentExportRequest(
      textArtifactId: json['text_artifact_id']?.toString() ?? '',
      textArtifactToken: json['text_artifact_token']?.toString() ?? '',
      exportFormat:
          DocumentExportFormat.fromString(json['export_format']?.toString()),
      metadataArtifactId: json['metadata_artifact_id']?.toString(),
      metadataArtifactToken: json['metadata_artifact_token']?.toString(),
    );
  }
}

class DocumentExportResult {
  const DocumentExportResult({
    required this.artifactId,
    required this.token,
    required this.format,
  });

  final String artifactId;
  final String token;
  final String format;

  factory DocumentExportResult.fromJson(Map<String, dynamic> json) {
    return DocumentExportResult(
      artifactId: json['artifact_id']?.toString() ?? '',
      token: json['token']?.toString() ?? '',
      format: json['format']?.toString() ?? 'markdown',
    );
  }

  Map<String, dynamic> toJson() => {
        'artifact_id': artifactId,
        'token': token,
        'format': format,
      };
}

class ExportDocxRequest {
  const ExportDocxRequest({this.text});

  final String? text;

  Map<String, dynamic> toJson() => {
        if (text != null) 'text': text,
      };

  factory ExportDocxRequest.fromJson(Map<String, dynamic> json) {
    return ExportDocxRequest(text: json['text']?.toString());
  }
}

class ExportHtmlRequest {
  const ExportHtmlRequest({
    required this.textArtifactId,
    required this.textArtifactToken,
  });

  final String textArtifactId;
  final String textArtifactToken;

  Map<String, dynamic> toJson() => {
        'text_artifact_id': textArtifactId,
        'text_artifact_token': textArtifactToken,
      };

  factory ExportHtmlRequest.fromJson(Map<String, dynamic> json) {
    return ExportHtmlRequest(
      textArtifactId: json['text_artifact_id']?.toString() ?? '',
      textArtifactToken: json['text_artifact_token']?.toString() ?? '',
    );
  }
}

class ExportBlockTreeRequest {
  const ExportBlockTreeRequest({
    required this.textArtifactId,
    required this.textArtifactToken,
    this.metadataArtifactId,
    this.metadataArtifactToken,
  });

  final String textArtifactId;
  final String textArtifactToken;
  final String? metadataArtifactId;
  final String? metadataArtifactToken;

  Map<String, dynamic> toJson() => {
        'text_artifact_id': textArtifactId,
        'text_artifact_token': textArtifactToken,
        if (metadataArtifactId != null)
          'metadata_artifact_id': metadataArtifactId,
        if (metadataArtifactToken != null)
          'metadata_artifact_token': metadataArtifactToken,
      };

  factory ExportBlockTreeRequest.fromJson(Map<String, dynamic> json) {
    return ExportBlockTreeRequest(
      textArtifactId: json['text_artifact_id']?.toString() ?? '',
      textArtifactToken: json['text_artifact_token']?.toString() ?? '',
      metadataArtifactId: json['metadata_artifact_id']?.toString(),
      metadataArtifactToken: json['metadata_artifact_token']?.toString(),
    );
  }
}
