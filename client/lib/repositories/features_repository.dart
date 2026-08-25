import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;
import 'package:omniscribe_client/models/translation.dart';
import 'package:omniscribe_client/models/transcription.dart';
import 'package:omniscribe_client/models/glossary.dart';
import 'package:omniscribe_client/models/extraction.dart';
import 'package:omniscribe_client/services/api_client.dart';

class FeaturesRepository {
  FeaturesRepository(this._apiClient);

  final ApiClient _apiClient;

  // Translation APIs
  Future<TranslationResponse> translate(TranslationRequest request) async {
    final res = await _apiClient.post('/translate', body: request.toJson());
    if (res is Map<String, dynamic>) {
      return TranslationResponse.fromJson(res);
    }
    throw ApiException('Invalid translation response');
  }

  Future<NLLBTranslationResponse> translateNllb({
    required String text,
    required String targetLanguage,
  }) async {
    final res = await _apiClient.post(
      '/translate/nllb',
      body: {'text': text, 'target_language': targetLanguage},
    );
    if (res is Map<String, dynamic>) {
      return NLLBTranslationResponse.fromJson(res);
    }
    throw ApiException('Invalid NLLB translation response');
  }

  Future<AsyncTranslationResponse> translateAsync(TranslationRequest request) async {
    final res = await _apiClient.post('/translate/async', body: request.toJson());
    if (res is Map<String, dynamic>) {
      return AsyncTranslationResponse.fromJson(res);
    }
    throw ApiException('Invalid async translation response');
  }

  Future<TranslationJobStatusResponse> getTranslationStatus(String jobId) async {
    final res = await _apiClient.get('/translate/status/$jobId');
    if (res is Map<String, dynamic>) {
      return TranslationJobStatusResponse.fromJson(res);
    }
    throw ApiException('Invalid translation status response');
  }

  // Transcription APIs
  Future<TranscriptionJobResponse> transcribe({
    required Uint8List fileBytes,
    required String filename,
    String engine = 'api',
    String model = 'whisper-1',
    String? language,
    String? prompt,
    double temperature = 0.0,
  }) async {
    final file = http.MultipartFile.fromBytes('file', fileBytes, filename: filename);
    final fields = <String, String>{
      'engine': engine,
      'model': model,
      if (language != null && language.isNotEmpty) 'language': language,
      if (prompt != null && prompt.isNotEmpty) 'prompt': prompt,
      'temperature': temperature.toString(),
    };

    final res = await _apiClient.postMultipart('/transcribe', files: [file], fields: fields);
    if (res is Map<String, dynamic>) {
      return TranscriptionJobResponse.fromJson(res);
    }
    throw ApiException('Invalid transcription response');
  }

  // Glossary APIs
  Future<List<GlossaryListItem>> getGlossaries() async {
    final res = await _apiClient.get('/glossary/library');
    if (res is List) {
      return res
          .whereType<Map<String, dynamic>>()
          .map((e) => GlossaryListItem.fromJson(e))
          .toList();
    }
    return const [];
  }

  Future<List<GlossaryEntry>> getGlossaryEntries(String id) async {
    final res = await _apiClient.get('/glossary/library/$id/entries');
    if (res is Map<String, dynamic> && res['entries'] is List) {
      return (res['entries'] as List)
          .whereType<Map<String, dynamic>>()
          .map((e) => GlossaryEntry.fromJson(e))
          .toList();
    } else if (res is List) {
      return res
          .whereType<Map<String, dynamic>>()
          .map((e) => GlossaryEntry.fromJson(e))
          .toList();
    }
    return const [];
  }

  Future<Map<String, String>> getMergedGlossary() async {
    final res = await _apiClient.get('/glossary/library/merged');
    if (res is Map<String, dynamic> && res['entries'] != null) {
      final entries = res['entries'];
      if (entries is Map<String, dynamic>) {
        return entries.map((key, value) => MapEntry(key, value.toString()));
      } else if (entries is List) {
        final map = <String, String>{};
        for (final item in entries) {
          if (item is Map<String, dynamic> && item['source'] != null && item['target'] != null) {
            map[item['source'].toString()] = item['target'].toString();
          }
        }
        return map;
      }
    }
    return const {};
  }

  Future<void> toggleGlossary(String id, bool enabled) async {
    await _apiClient.post('/glossary/library/$id/enable', body: {'enabled': enabled});
  }

  Future<void> deleteGlossary(String id) async {
    await _apiClient.delete('/glossary/library/$id');
  }

  Future<GlossaryImportJobResponse> importGlossaryJson({
    required String format,
    String? name,
    String? text,
    String? inlineBytesB64,
  }) async {
    final payload = {
      'source': {
        'format': format,
        if (name != null) 'name': name,
        if (text != null) 'text': text,
        if (inlineBytesB64 != null) 'inline_bytes_b64': inlineBytesB64,
      }
    };
    final res = await _apiClient.post('/glossary/import', body: payload);
    if (res is Map<String, dynamic>) {
      return GlossaryImportJobResponse.fromJson(res);
    }
    throw ApiException('Invalid glossary import response');
  }

  Future<GlossaryImportJobResponse> importGlossaryUrl({
    required String url,
    required String format,
    String? name,
  }) async {
    final res = await _apiClient.post(
      '/glossary/import/url',
      body: {'url': url, 'format': format, if (name != null) 'name': name},
    );
    if (res is Map<String, dynamic>) {
      return GlossaryImportJobResponse.fromJson(res);
    }
    throw ApiException('Invalid glossary URL import response');
  }

  // Extraction & Export APIs
  Future<ExtractionResponse> extract(ExtractionRequest request) async {
    final res = await _apiClient.post('/extract', body: request.toJson());
    if (res is Map<String, dynamic>) {
      return ExtractionResponse.fromJson(res);
    }
    throw ApiException('Invalid extraction response');
  }

  Future<Uint8List> exportHtml(String artifactId, String token) async {
    return _apiClient.getBytes(
      '/export/html',
      headers: {'Authorization': 'Bearer $token'},
    );
  }

  Future<Uint8List> exportDocxTree(String artifactId, String token) async {
    return _apiClient.getBytes(
      '/export/docx-tree',
      headers: {'Authorization': 'Bearer $token'},
    );
  }

  Future<dynamic> exportBlockTree(String artifactId, String token) async {
    return _apiClient.get(
      '/export/blocktree',
      headers: {'Authorization': 'Bearer $token'},
    );
  }
}
