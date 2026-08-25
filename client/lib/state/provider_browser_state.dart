import 'package:omniscribe_client/models/provider.dart';

class ProviderBrowserState {
  const ProviderBrowserState({
    this.providers = const [],
    this.activeProvider,
    this.validationStatus = const {},
    this.modelsMap = const {},
    this.loadingModelIds = const {},
    this.isFetching = false,
    this.isValidating = false,
    this.searchQuery = '',
    this.error,
  });

  final List<ProviderPreset> providers;
  final ProviderPreset? activeProvider;
  final Map<String, String> validationStatus;
  final Map<String, List<String>> modelsMap;
  final Set<String> loadingModelIds;
  final bool isFetching;
  final bool isValidating;
  final String searchQuery;
  final String? error;

  List<ProviderPreset> get filteredProviders {
    if (searchQuery.trim().isEmpty) return providers;
    final q = searchQuery.toLowerCase().trim();
    return providers.where((p) {
      final name = p.name.toLowerCase();
      final desc = p.description.toLowerCase();
      final id = p.id.toLowerCase();
      final cat = p.category.toLowerCase();
      final hasModel = p.models.any((m) => m.toLowerCase().contains(q));
      return name.contains(q) || desc.contains(q) || id.contains(q) || cat.contains(q) || hasModel;
    }).toList();
  }

  List<ProviderPreset> get popularProviders =>
      filteredProviders.where((p) => p.category == 'popular').toList();

  List<ProviderPreset> get otherProviders =>
      filteredProviders.where((p) => p.category != 'popular').toList();

  ProviderBrowserState copyWith({
    List<ProviderPreset>? providers,
    ProviderPreset? activeProvider,
    bool clearActiveProvider = false,
    Map<String, String>? validationStatus,
    Map<String, List<String>>? modelsMap,
    Set<String>? loadingModelIds,
    bool? isFetching,
    bool? isValidating,
    String? searchQuery,
    String? error,
    bool clearError = false,
  }) {
    return ProviderBrowserState(
      providers: providers ?? this.providers,
      activeProvider: clearActiveProvider ? null : (activeProvider ?? this.activeProvider),
      validationStatus: validationStatus ?? this.validationStatus,
      modelsMap: modelsMap ?? this.modelsMap,
      loadingModelIds: loadingModelIds ?? this.loadingModelIds,
      isFetching: isFetching ?? this.isFetching,
      isValidating: isValidating ?? this.isValidating,
      searchQuery: searchQuery ?? this.searchQuery,
      error: clearError ? null : (error ?? this.error),
    );
  }
}
