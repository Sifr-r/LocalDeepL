import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/enums/app_tab.dart';
import 'package:omniscribe_client/core/enums/server_health.dart';

/// Active navigation tab in OmniScribe.
final activeTabProvider = StateProvider<AppTab>((ref) => AppTab.workstation);

/// Current theme mode (Dark is default in DocuVerse).
final themeModeProvider = StateProvider<ThemeMode>((ref) => ThemeMode.dark);

/// Selected LLM / OCR provider preset name.
final activeProviderPresetProvider =
    StateProvider<String>((ref) => 'Ollama (Local)');

/// Server health model.
@immutable
class ServerHealthState {
  const ServerHealthState({
    required this.status,
    this.latencyMs,
    this.endpoint = 'http://localhost:8000',
    this.version = 'v2.0.0',
    this.lastChecked,
    this.error,
  });

  final ServerHealth status;
  final int? latencyMs;
  final String endpoint;
  final String version;
  final DateTime? lastChecked;
  final String? error;

  ServerHealthState copyWith({
    ServerHealth? status,
    int? latencyMs,
    String? endpoint,
    String? version,
    DateTime? lastChecked,
    String? error,
  }) {
    return ServerHealthState(
      status: status ?? this.status,
      latencyMs: latencyMs ?? this.latencyMs,
      endpoint: endpoint ?? this.endpoint,
      version: version ?? this.version,
      lastChecked: lastChecked ?? this.lastChecked,
      error: error ?? this.error,
    );
  }
}

/// Riverpod StateNotifier for Server Health monitoring.
class ServerHealthNotifier extends StateNotifier<ServerHealthState> {
  ServerHealthNotifier()
      : super(ServerHealthState(
          status: ServerHealth.online,
          latencyMs: 38,
          lastChecked: DateTime.now(),
        ));

  void setChecking() {
    state = state.copyWith(status: ServerHealth.checking);
  }

  void setOnline({int? latencyMs, String? version}) {
    state = state.copyWith(
      status: ServerHealth.online,
      latencyMs: latencyMs ?? state.latencyMs,
      version: version ?? state.version,
      lastChecked: DateTime.now(),
      error: null,
    );
  }

  void setOffline({String? error}) {
    state = state.copyWith(
      status: ServerHealth.offline,
      latencyMs: null,
      lastChecked: DateTime.now(),
      error: error,
    );
  }
}

/// Provider for server health state.
final serverHealthProvider =
    StateNotifierProvider<ServerHealthNotifier, ServerHealthState>((ref) {
  return ServerHealthNotifier();
});
