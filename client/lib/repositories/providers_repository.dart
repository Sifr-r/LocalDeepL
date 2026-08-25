import 'package:omniscribe_client/models/provider.dart';
import 'package:omniscribe_client/services/api_client.dart';

class ProvidersRepository {
  ProvidersRepository(this._apiClient);

  final ApiClient _apiClient;

  Future<List<ProviderPreset>> getProviders() async {
    final res = await _apiClient.get('/providers');
    if (res is Map<String, dynamic> && res['providers'] is List) {
      return (res['providers'] as List)
          .whereType<Map<String, dynamic>>()
          .map((e) => ProviderPreset.fromJson(e))
          .toList();
    }
    return const [];
  }

  Future<ProviderPreset> getProviderDetails(String id) async {
    final res = await _apiClient.get('/providers/$id');
    if (res is Map<String, dynamic>) {
      return ProviderPreset.fromJson(res);
    }
    throw ApiException('Failed to load provider $id');
  }

  Future<List<String>> getProviderModels(String id) async {
    try {
      final res = await _apiClient.get('/providers/$id/models');
      if (res is Map<String, dynamic> && res['models'] is List) {
        return (res['models'] as List).map((e) => e.toString()).toList();
      }
    } catch (_) {}
    return const [];
  }

  Future<SetActiveProviderResponse> setActiveProvider({
    required String providerId,
    String? apiBase,
    String? apiKey,
    String? model,
  }) async {
    final res = await _apiClient.post(
      '/providers/active',
      body: {
        'provider_id': providerId,
        if (apiBase != null) 'api_base': apiBase,
        if (apiKey != null) 'api_key': apiKey,
        if (model != null) 'model': model,
      },
    );
    if (res is Map<String, dynamic>) {
      return SetActiveProviderResponse.fromJson(res);
    }
    throw ApiException('Failed to set active provider');
  }

  Future<ValidateProviderResponse> validateProvider({
    required String providerId,
    required String apiBase,
    String? apiKey,
    String? model,
  }) async {
    final res = await _apiClient.post(
      '/providers/validate',
      body: {
        'provider_id': providerId,
        'api_base': apiBase,
        if (apiKey != null && apiKey.isNotEmpty) 'api_key': apiKey,
        if (model != null && model.isNotEmpty) 'model': model,
      },
    );
    if (res is Map<String, dynamic>) {
      return ValidateProviderResponse.fromJson(res);
    }
    throw ApiException('Failed to validate provider');
  }
}
