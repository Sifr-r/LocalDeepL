import 'package:omniscribe_client/core/constants/api_constants.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';

abstract class ConfigRepository {
  /// Fetch the active server runtime configuration.
  Future<RuntimeConfig> getConfig();

  /// Update server runtime configuration options.
  Future<RuntimeConfig> updateConfig(ConfigUpdate updates);

  /// Fetch list of supported models under the given namespace (general, ocr, translation, transcription).
  Future<List<String>> getModels({String namespace = 'general'});
}

class ConfigRepositoryImpl implements ConfigRepository {
  const ConfigRepositoryImpl(this._apiClient);

  final ApiClient _apiClient;

  @override
  Future<RuntimeConfig> getConfig() async {
    final json = await _apiClient.get<Map<String, dynamic>>(
      ApiConstants.config,
    );
    return RuntimeConfig.fromJson(json);
  }

  @override
  Future<RuntimeConfig> updateConfig(ConfigUpdate updates) async {
    final json = await _apiClient.post<Map<String, dynamic>>(
      ApiConstants.config,
      data: updates.toJson(),
    );
    return RuntimeConfig.fromJson(json);
  }

  @override
  Future<List<String>> getModels({String namespace = 'general'}) async {
    final endpoint = namespace.isNotEmpty && namespace != 'general'
        ? '${ApiConstants.models}/$namespace'
        : ApiConstants.models;

    final json = await _apiClient.get<Map<String, dynamic>>(endpoint);
    final list = <String>[];
    if (json['models'] is List) {
      for (final item in json['models'] as List) {
        if (item != null) list.add(item.toString());
      }
    }
    return list;
  }
}
