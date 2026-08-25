/// Structured information extraction models.
class ExtractionRequest {
  const ExtractionRequest({
    this.text,
    this.template = 'invoice',
    this.customPrompt,
    this.apiBase,
    this.apiKey,
    this.model,
  });

  final String? text;
  final String template;
  final String? customPrompt;
  final String? apiBase;
  final String? apiKey;
  final String? model;

  Map<String, dynamic> toJson() {
    return {
      if (text != null) 'text': text,
      'template': template,
      if (customPrompt != null) 'custom_prompt': customPrompt,
      if (apiBase != null) 'api_base': apiBase,
      if (apiKey != null) 'api_key': apiKey,
      if (model != null) 'model': model,
    };
  }
}

class ExtractionResponse {
  const ExtractionResponse({
    required this.extractedData,
  });

  final dynamic extractedData;

  factory ExtractionResponse.fromJson(Map<String, dynamic> json) {
    return ExtractionResponse(
      extractedData: json['extracted_data'] ?? json['data'] ?? json,
    );
  }
}
