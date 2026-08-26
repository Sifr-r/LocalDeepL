/// Glossary and terminology management models.
class GlossaryListItem {
  const GlossaryListItem({
    required this.id,
    required this.name,
    this.format = 'json_pairs',
    this.entryCount = 0,
    this.enabled = true,
    this.priority = 1,
    this.sourceUri,
    this.group = 'default',
  });

  final String id;
  final String name;
  final String format;
  final int entryCount;
  final bool enabled;
  final int priority;
  final String? sourceUri;
  final String group;

  factory GlossaryListItem.fromJson(Map<String, dynamic> json) {
    return GlossaryListItem(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? 'Untitled Glossary',
      format: json['format'] as String? ?? 'json_pairs',
      entryCount: (json['entry_count'] as num?)?.toInt() ?? 0,
      enabled: json['enabled'] as bool? ?? true,
      priority: (json['priority'] as num?)?.toInt() ?? 1,
      sourceUri: json['source_uri'] as String?,
      group: json['group'] as String? ?? 'default',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'format': format,
      'entry_count': entryCount,
      'enabled': enabled,
      'priority': priority,
      if (sourceUri != null) 'source_uri': sourceUri,
      'group': group,
    };
  }

  GlossaryListItem copyWith({
    String? id,
    String? name,
    String? format,
    int? entryCount,
    bool? enabled,
    int? priority,
    String? sourceUri,
    String? group,
  }) {
    return GlossaryListItem(
      id: id ?? this.id,
      name: name ?? this.name,
      format: format ?? this.format,
      entryCount: entryCount ?? this.entryCount,
      enabled: enabled ?? this.enabled,
      priority: priority ?? this.priority,
      sourceUri: sourceUri ?? this.sourceUri,
      group: group ?? this.group,
    );
  }
}

class GlossaryEntry {
  const GlossaryEntry({
    required this.source,
    required this.target,
    this.note,
  });

  final String source;
  final String target;
  final String? note;

  factory GlossaryEntry.fromJson(Map<String, dynamic> json) {
    return GlossaryEntry(
      source: json['source'] as String? ?? '',
      target: json['target'] as String? ?? '',
      note: json['note'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'source': source,
      'target': target,
      if (note != null) 'note': note,
    };
  }
}

class GlossaryImportJobResponse {
  const GlossaryImportJobResponse({
    this.glossaryId,
    this.jobId,
    this.format = 'json_pairs',
    required this.name,
    this.entryCount = 0,
    this.warnings = const [],
    this.queued = false,
  });

  final String? glossaryId;
  final String? jobId;
  final String format;
  final String name;
  final int entryCount;
  final List<String> warnings;
  final bool queued;

  factory GlossaryImportJobResponse.fromJson(Map<String, dynamic> json) {
    return GlossaryImportJobResponse(
      glossaryId: json['glossary_id'] as String?,
      jobId: json['job_id'] as String?,
      format: json['format'] as String? ?? 'json_pairs',
      name: json['name'] as String? ?? 'Imported Glossary',
      entryCount: (json['entry_count'] as num?)?.toInt() ?? 0,
      warnings: (json['warnings'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const [],
      queued: json['queued'] as bool? ?? false,
    );
  }
}
