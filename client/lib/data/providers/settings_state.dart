import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';

@immutable
class SettingsState {
  const SettingsState({
    required this.isLoading,
    required this.runtimeConfig,
    required this.activeProviderId,
    required this.ocrModels,
    required this.translationModels,
    required this.transcriptionModels,
    required this.serverBaseUrl,
    required this.useAsync,
    required this.error,
    required this.isDarkMode,
  });

  /// Initial empty state — no config fetched, no errors, default provider.
  const SettingsState.initial()
      : isLoading = false,
        runtimeConfig = null,
        activeProviderId = 'openai',
        ocrModels = const <String>[],
        translationModels = const <String>[],
        transcriptionModels = const <String>[],
        serverBaseUrl = 'http://127.0.0.1:8000',
        useAsync = false,
        error = null,
        isDarkMode = false;

  final bool isLoading;
  final RuntimeConfig? runtimeConfig;
  final String activeProviderId;
  final List<String> ocrModels;
  final List<String> translationModels;
  final List<String> transcriptionModels;
  final String serverBaseUrl;
  final bool useAsync;
  final String? error;
  final bool isDarkMode;

  SettingsState copyWith({
    bool? isLoading,
    RuntimeConfig? runtimeConfig,
    String? activeProviderId,
    List<String>? ocrModels,
    List<String>? translationModels,
    List<String>? transcriptionModels,
    String? serverBaseUrl,
    bool? useAsync,
    String? error,
    bool? isDarkMode,
    bool clearError = false,
    bool clearRuntimeConfig = false,
  }) {
    return SettingsState(
      isLoading: isLoading ?? this.isLoading,
      runtimeConfig:
          clearRuntimeConfig ? null : (runtimeConfig ?? this.runtimeConfig),
      activeProviderId: activeProviderId ?? this.activeProviderId,
      ocrModels: ocrModels ?? this.ocrModels,
      translationModels: translationModels ?? this.translationModels,
      transcriptionModels: transcriptionModels ?? this.transcriptionModels,
      serverBaseUrl: serverBaseUrl ?? this.serverBaseUrl,
      useAsync: useAsync ?? this.useAsync,
      error: clearError ? null : (error ?? this.error),
      isDarkMode: isDarkMode ?? this.isDarkMode,
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is SettingsState &&
        other.isLoading == isLoading &&
        other.runtimeConfig == runtimeConfig &&
        other.activeProviderId == activeProviderId &&
        listEquals(other.ocrModels, ocrModels) &&
        listEquals(other.translationModels, translationModels) &&
        listEquals(other.transcriptionModels, transcriptionModels) &&
        other.serverBaseUrl == serverBaseUrl &&
        other.useAsync == useAsync &&
        other.error == error &&
        other.isDarkMode == isDarkMode;
  }

  @override
  int get hashCode => Object.hash(
        isLoading,
        runtimeConfig,
        activeProviderId,
        Object.hashAll(ocrModels),
        Object.hashAll(translationModels),
        Object.hashAll(transcriptionModels),
        serverBaseUrl,
        useAsync,
        error,
        isDarkMode,
      );
}
