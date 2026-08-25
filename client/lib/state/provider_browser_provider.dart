import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/models/provider.dart';
import 'package:omniscribe_client/repositories/providers_repository.dart';
import 'package:omniscribe_client/services/api_client.dart';
import 'provider_browser_state.dart';

/// Stack A HTTP client provider — kept here because Stack A repositories
/// (jobs/features/providers) still wrap the legacy `package:http`-based
/// `ApiClient`. Migrated to Stack B's Dio client in slices 4–6.
final legacyApiClientProvider = Provider<ApiClient>((ref) => ApiClient());

final providersRepositoryProvider = Provider<ProvidersRepository>((ref) {
  final client = ref.watch(legacyApiClientProvider);
  return ProvidersRepository(client);
});

final providerBrowserProvider =
    StateNotifierProvider<ProviderBrowserNotifier, ProviderBrowserState>((ref) {
  final repository = ref.watch(providersRepositoryProvider);
  return ProviderBrowserNotifier(repository, ref);
});

class ProviderBrowserNotifier extends StateNotifier<ProviderBrowserState> {
  ProviderBrowserNotifier(this._repository, Ref ref)
      : _ref = ref,
        super(const ProviderBrowserState()) {
    fetchProviders();
  }

  final ProvidersRepository _repository;
  final Ref _ref;

  Future<void> fetchProviders() async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final providers = await _repository.getProviders();
      state = state.copyWith(providers: providers, isFetching: false);
      for (final provider in providers) {
        if (provider.recommendedBaseUrl.isNotEmpty &&
            !provider.recommendedBaseUrl.contains('<') &&
            !provider.recommendedBaseUrl.contains('{')) {
          fetchModelsForProvider(provider.id);
        }
      }
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
    }
  }

  Future<void> fetchModelsForProvider(String id) async {
    if (state.loadingModelIds.contains(id)) return;

    final newLoading = Set<String>.from(state.loadingModelIds)..add(id);
    state = state.copyWith(loadingModelIds: newLoading);

    try {
      final models = await _repository.getProviderModels(id);
      final newModelsMap = Map<String, List<String>>.from(state.modelsMap);
      if (models.isNotEmpty) {
        newModelsMap[id] = models;
      }
      final updatedLoading = Set<String>.from(state.loadingModelIds)..remove(id);
      state = state.copyWith(
        modelsMap: newModelsMap,
        loadingModelIds: updatedLoading,
      );
    } catch (_) {
      final updatedLoading = Set<String>.from(state.loadingModelIds)..remove(id);
      state = state.copyWith(loadingModelIds: updatedLoading);
    }
  }

  Future<ValidateProviderResponse> validateProvider(
    String id,
    String base,
    String? key, {
    String? model,
  }) async {
    state = state.copyWith(isValidating: true);
    try {
      final res = await _repository.validateProvider(
        providerId: id,
        apiBase: base,
        apiKey: key,
        model: model,
      );
      final newStatus = Map<String, String>.from(state.validationStatus);
      newStatus[id] = res.valid
          ? 'Connected successfully (${res.modelCount} models)'
          : (res.error ?? 'Validation failed');
      state = state.copyWith(
        validationStatus: newStatus,
        isValidating: false,
      );
      if (res.valid) {
        fetchModelsForProvider(id);
      }
      return res;
    } catch (e) {
      final newStatus = Map<String, String>.from(state.validationStatus);
      newStatus[id] = e.toString();
      state = state.copyWith(validationStatus: newStatus, isValidating: false);
      return ValidateProviderResponse(valid: false, error: e.toString());
    }
  }

  Future<void> setActiveProvider(
    String id,
    String? apiBase,
    String? apiKey,
    String? model,
  ) async {
    state = state.copyWith(isFetching: true, clearError: true);
    try {
      final res = await _repository.setActiveProvider(
        providerId: id,
        apiBase: apiBase,
        apiKey: apiKey,
        model: model,
      );
      _ref.read(settingsStateProvider.notifier).setActiveProvider(id);
      await _ref.read(settingsStateProvider.notifier).load();
      state = state.copyWith(isFetching: false);
    } catch (e) {
      state = state.copyWith(isFetching: false, error: e.toString());
      rethrow;
    }
  }

  void setSearchQuery(String query) {
    state = state.copyWith(searchQuery: query);
  }

  void selectActiveProvider(ProviderPreset? provider) {
    state = state.copyWith(activeProvider: provider);
  }
}
