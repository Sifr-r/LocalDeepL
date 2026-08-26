import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/provider_repository.dart';

/// Riverpod entry-point for the Provider Browser feature.
///
/// Wires `data/repositories/provider_repository.dart` to a
/// `ProviderBrowserState` and exposes the same verb set the legacy
/// `state/provider_browser_provider.dart` did:
/// `fetchProviders`, `fetchModelsForProvider`, `validateProvider`,
/// `setActiveProvider`, `setSearchQuery`, `selectActiveProvider`.
final providerBrowserProvider =
    NotifierProvider<ProviderBrowserNotifier, ProviderBrowserState>(
  ProviderBrowserNotifier.new,
);

class ProviderBrowserNotifier extends Notifier<ProviderBrowserState> {
  late final ProviderRepository _repo;

  @override
  ProviderBrowserState build() {
    _repo = ref.watch(providerRepositoryProvider);
    return const ProviderBrowserState.initial();
  }

  Future<void> fetchProviders() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final providers = await _repo.getProviders();
      state = state.copyWith(providers: providers, isFetching: false);
      // Auto-fetch models for providers whose `recommendedBaseUrl` is
      // a concrete URL (no template placeholders like `{host}`).
      for (final provider in providers) {
        if (provider.recommendedBaseUrl.isNotEmpty &&
            !provider.recommendedBaseUrl.contains('<') &&
            !provider.recommendedBaseUrl.contains('{')) {
          // Intentionally not awaited — fire-and-forget; per-provider
          // state updates land via `fetchModelsForProvider`. The legacy
          // behaviour was the same.
          // ignore: unawaited_futures
          fetchModelsForProvider(provider.id);
        }
      }
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  // Stub for Task 3 — replaced by the real implementation in the next task.
  // ignore: body_might_complete_normally
  Future<void> fetchModelsForProvider(String id) async {}
}
