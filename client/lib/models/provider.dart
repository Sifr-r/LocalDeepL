/// LLM Provider preset and connection models.
class ProviderPreset {
  const ProviderPreset({
    required this.id,
    required this.name,
    this.category = 'popular',
    this.description = '',
    this.recommendedBaseUrl = '',
    this.apiBase,
    this.defaultModel = '',
    this.models = const [],
    this.requiresKey = true,
    this.envKeys = const [],
    this.docUrl,
    this.getApiKeyUrl,
    this.isRecommended = false,
    this.isCustom = false,
    this.iconId,
    this.notes = '',
  });

  final String id;
  final String name;
  final String category;
  final String description;
  final String recommendedBaseUrl;
  final String? apiBase;
  final String defaultModel;
  final List<String> models;
  final bool requiresKey;
  final List<String> envKeys;
  final String? docUrl;
  final String? getApiKeyUrl;
  final bool isRecommended;
  final bool isCustom;
  final String? iconId;
  final String notes;

  factory ProviderPreset.fromJson(Map<String, dynamic> json) {
    return ProviderPreset(
      id: json['id'] as String? ?? '',
      name: json['name'] as String? ?? json['display_name'] as String? ?? '',
      category: json['category'] as String? ?? 'popular',
      description: json['description'] as String? ?? '',
      recommendedBaseUrl: json['recommended_base_url'] as String? ?? json['api_url'] as String? ?? '',
      apiBase: json['api_base'] as String? ?? json['api_url'] as String?,
      defaultModel: json['default_model'] as String? ?? '',
      models: (json['models'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? const [],
      requiresKey: json['requires_key'] as bool? ?? json['requires_auth'] as bool? ?? true,
      envKeys: (json['env_keys'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? const [],
      docUrl: json['doc_url'] as String?,
      getApiKeyUrl: json['get_api_key_url'] as String?,
      isRecommended: json['is_recommended'] as bool? ?? false,
      isCustom: json['is_custom'] as bool? ?? false,
      iconId: json['icon_id'] as String?,
      notes: json['notes'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'category': category,
      'description': description,
      'recommended_base_url': recommendedBaseUrl,
      if (apiBase != null) 'api_base': apiBase,
      'default_model': defaultModel,
      'models': models,
      'requires_key': requiresKey,
      'env_keys': envKeys,
      if (docUrl != null) 'doc_url': docUrl,
      if (getApiKeyUrl != null) 'get_api_key_url': getApiKeyUrl,
      'is_recommended': isRecommended,
      'is_custom': isCustom,
      if (iconId != null) 'icon_id': iconId,
      'notes': notes,
    };
  }

  ProviderPreset copyWith({
    String? id,
    String? name,
    String? category,
    String? description,
    String? recommendedBaseUrl,
    String? apiBase,
    String? defaultModel,
    List<String>? models,
    bool? requiresKey,
    List<String>? envKeys,
    String? docUrl,
    String? getApiKeyUrl,
    bool? isRecommended,
    bool? isCustom,
    String? iconId,
    String? notes,
  }) {
    return ProviderPreset(
      id: id ?? this.id,
      name: name ?? this.name,
      category: category ?? this.category,
      description: description ?? this.description,
      recommendedBaseUrl: recommendedBaseUrl ?? this.recommendedBaseUrl,
      apiBase: apiBase ?? this.apiBase,
      defaultModel: defaultModel ?? this.defaultModel,
      models: models ?? this.models,
      requiresKey: requiresKey ?? this.requiresKey,
      envKeys: envKeys ?? this.envKeys,
      docUrl: docUrl ?? this.docUrl,
      getApiKeyUrl: getApiKeyUrl ?? this.getApiKeyUrl,
      isRecommended: isRecommended ?? this.isRecommended,
      isCustom: isCustom ?? this.isCustom,
      iconId: iconId ?? this.iconId,
      notes: notes ?? this.notes,
    );
  }
}

class ValidateProviderResponse {
  const ValidateProviderResponse({
    required this.valid,
    this.modelCount = 0,
    this.error,
  });

  final bool valid;
  final int modelCount;
  final String? error;

  factory ValidateProviderResponse.fromJson(Map<String, dynamic> json) {
    return ValidateProviderResponse(
      valid: json['valid'] as bool? ?? false,
      modelCount: (json['model_count'] as num?)?.toInt() ?? 0,
      error: json['error'] as String?,
    );
  }
}

class SetActiveProviderResponse {
  const SetActiveProviderResponse({
    required this.apiBase,
    required this.model,
  });

  final String apiBase;
  final String model;

  factory SetActiveProviderResponse.fromJson(Map<String, dynamic> json) {
    return SetActiveProviderResponse(
      apiBase: json['api_base'] as String? ?? '',
      model: json['model'] as String? ?? '',
    );
  }
}
