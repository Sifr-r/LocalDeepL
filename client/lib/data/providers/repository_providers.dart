import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/core/websocket/ws_client.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';
import 'package:omniscribe_client/data/repositories/feature_repository.dart';
import 'package:omniscribe_client/data/repositories/job_repository.dart';
import 'package:omniscribe_client/data/repositories/ocr_repository.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

/// Base URL provider for the OmniScribe backend server.
final apiBaseUrlProvider =
    StateProvider<String>((ref) => 'http://127.0.0.1:8000');

/// Global/active auth token provider.
final authTokenProvider = StateProvider<String?>((ref) => null);

/// Core ApiClient provider.
final apiClientProvider = Provider<ApiClient>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  final client = ApiClient(
    baseUrl: baseUrl,
    authTokenProvider: () => ref.read(authTokenProvider),
  );
  return client;
});

/// WebSocket Client provider.
final wsClientProvider = Provider<WsClient>((ref) {
  final baseUrl = ref.watch(apiBaseUrlProvider);
  final wsUrl = baseUrl.replaceFirst(RegExp(r'^http'), 'ws');
  final ws = WsClient(defaultWsBaseUrl: wsUrl);
  ref.onDispose(ws.dispose);
  return ws;
});

/// OCR Repository provider.
final ocrRepositoryProvider = Provider<OcrRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return OcrRepositoryImpl(apiClient);
});

/// Provider Catalog & Discovery Repository provider.
final providerRepositoryProvider = Provider<ProviderRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return ProviderRepositoryImpl(apiClient);
});

/// Config Repository provider.
final configRepositoryProvider = Provider<ConfigRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return ConfigRepositoryImpl(apiClient);
});

/// Job History & Queue Repository provider.
final jobRepositoryProvider = Provider<JobRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return JobRepositoryImpl(apiClient);
});

/// Feature Repository provider (translation, transcription, extraction, glossary, export).
final featureRepositoryProvider = Provider<FeatureRepository>((ref) {
  final apiClient = ref.watch(apiClientProvider);
  return FeatureRepositoryImpl(apiClient);
});
