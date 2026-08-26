import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/data/providers/provider_browser_state.dart';
import 'package:omniscribe_client/data/providers/provider_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_modal.dart';
import 'provider_card.dart';

class ProviderModal extends ConsumerStatefulWidget {
  const ProviderModal({
    super.key,
    this.initialProvider,
    this.targetNamespace = 'ocr',
    this.onApplied,
  });

  final ProviderPreset? initialProvider;
  final String targetNamespace;
  final VoidCallback? onApplied;

  static Future<void> show(
    BuildContext context, {
    ProviderPreset? initialProvider,
    String targetNamespace = 'ocr',
    VoidCallback? onApplied,
  }) {
    return DocuVerseModal.show(
      context: context,
      title: 'LLM Provider Browser',
      description: 'Select and configure AI model endpoints for $targetNamespace processing',
      maxWidth: 720,
      child: ProviderModal(
        initialProvider: initialProvider,
        targetNamespace: targetNamespace,
        onApplied: onApplied,
      ),
    );
  }

  @override
  ConsumerState<ProviderModal> createState() => _ProviderModalState();
}

class _ProviderModalState extends ConsumerState<ProviderModal> {
  ProviderPreset? _selectedProvider;
  late TextEditingController _apiBaseController;
  late TextEditingController _apiKeyController;
  late TextEditingController _modelController;
  late TextEditingController _searchController;
  String? _testMessage;
  bool _testSuccess = false;
  bool _isTesting = false;
  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    _selectedProvider = widget.initialProvider;
    _apiBaseController = TextEditingController();
    _apiKeyController = TextEditingController();
    _modelController = TextEditingController();
    _searchController = TextEditingController();

    if (_selectedProvider != null) {
      _initFormForProvider(_selectedProvider!);
    }
  }

  void _initFormForProvider(ProviderPreset provider) {
    _apiBaseController.text = provider.apiBase ?? provider.recommendedBaseUrl;
    _apiKeyController.text = '';
    _modelController.text = provider.defaultModel.isNotEmpty
        ? provider.defaultModel
        : (provider.models.isNotEmpty ? provider.models.first : '');
    _testMessage = null;
    _testSuccess = false;
  }

  @override
  void dispose() {
    _apiBaseController.dispose();
    _apiKeyController.dispose();
    _modelController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _runConnectionTest() async {
    if (_selectedProvider == null) return;
    setState(() {
      _isTesting = true;
      _testMessage = null;
    });

    final notifier = ref.read(providerBrowserProvider.notifier);
    final res = await notifier.validateProvider(
      _selectedProvider!.id,
      _apiBaseController.text.trim(),
      _apiKeyController.text.trim().isNotEmpty ? _apiKeyController.text.trim() : null,
      model: _modelController.text.trim().isNotEmpty ? _modelController.text.trim() : null,
    );

    if (mounted) {
      setState(() {
        _isTesting = false;
        _testSuccess = res.valid;
        _testMessage = res.valid
            ? 'Endpoint reachable! Found ${res.modelCount} models.'
            : (res.error ?? 'Validation failed');
      });
    }
  }

  Future<void> _applyProvider() async {
    if (_selectedProvider == null) return;
    setState(() {
      _isSaving = true;
    });

    try {
      final notifier = ref.read(providerBrowserProvider.notifier);
      await notifier.setActiveProvider(
        _selectedProvider!.id,
        _apiBaseController.text.trim(),
        _apiKeyController.text.trim().isNotEmpty ? _apiKeyController.text.trim() : null,
        _modelController.text.trim().isNotEmpty ? _modelController.text.trim() : null,
      );

      if (mounted) {
        widget.onApplied?.call();
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _testSuccess = false;
          _testMessage = 'Failed to apply provider: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(providerBrowserProvider);
    final config = ref.watch(settingsStateProvider);
    final tokens = context.docuVerse;

    if (_selectedProvider != null) {
      return _buildConnectForm(tokens, state);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Search bar
        DocuVerseInput(
          controller: _searchController,
          placeholder: 'Search providers (e.g. OpenAI, Anthropic, Ollama, LM Studio...)',
          prefixIcon: Icon(Icons.search, size: 16, color: tokens.foregroundMuted),
          onChanged: (q) => ref.read(providerBrowserProvider.notifier).setSearchQuery(q),
        ),
        const SizedBox(height: 16),

        if (state.isFetching && state.providers.isEmpty) ...[
          Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(tokens.brand),
              ),
            ),
          ),
        ] else if (state.filteredProviders.isEmpty) ...[
          Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Text(
                'No providers found matching "${_searchController.text}".',
                style: TextStyle(color: tokens.foregroundMuted, fontSize: 13),
              ),
            ),
          ),
        ] else ...[
          // Popular Section
          if (state.popularProviders.isNotEmpty) ...[
            Text(
              'POPULAR PROVIDERS',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: tokens.foregroundMuted,
                letterSpacing: 0.8,
              ),
            ),
            const SizedBox(height: 8),
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: state.popularProviders.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final p = state.popularProviders[index];
                final models = state.modelsMap[p.id] ?? const [];
                final isLoading = state.loadingModelIds.contains(p.id);
                final isActive = config.activeProviderId == p.id;

                return ProviderCard(
                  provider: p,
                  models: models,
                  isLoadingModels: isLoading,
                  isActive: isActive,
                  onConnect: () {
                    setState(() {
                      _selectedProvider = p;
                      _initFormForProvider(p);
                    });
                  },
                  onUseModel: (model) async {
                    _selectedProvider = p;
                    _initFormForProvider(p);
                    _modelController.text = model;
                    await _applyProvider();
                  },
                  onRefreshModels: () =>
                      ref.read(providerBrowserProvider.notifier).fetchModelsForProvider(p.id),
                );
              },
            ),
            const SizedBox(height: 16),
          ],

          // Other / Local / Custom Section
          if (state.otherProviders.isNotEmpty) ...[
            Text(
              'LOCAL & CLOUD PROVIDERS',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: tokens.foregroundMuted,
                letterSpacing: 0.8,
              ),
            ),
            const SizedBox(height: 8),
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: state.otherProviders.length,
              separatorBuilder: (_, __) => const SizedBox(height: 8),
              itemBuilder: (context, index) {
                final p = state.otherProviders[index];
                final models = state.modelsMap[p.id] ?? const [];
                final isLoading = state.loadingModelIds.contains(p.id);
                final isActive = config.activeProviderId == p.id;

                return ProviderCard(
                  provider: p,
                  models: models,
                  isLoadingModels: isLoading,
                  isActive: isActive,
                  onConnect: () {
                    setState(() {
                      _selectedProvider = p;
                      _initFormForProvider(p);
                    });
                  },
                  onUseModel: (model) async {
                    _selectedProvider = p;
                    _initFormForProvider(p);
                    _modelController.text = model;
                    await _applyProvider();
                  },
                  onRefreshModels: () =>
                      ref.read(providerBrowserProvider.notifier).fetchModelsForProvider(p.id),
                );
              },
            ),
          ],
        ],
      ],
    );
  }

  Widget _buildConnectForm(DocuVerseThemeTokens tokens, ProviderBrowserState state) {
    final p = _selectedProvider!;
    final availableModels = state.modelsMap[p.id] ?? p.models;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Back link + Provider Header
        Row(
          children: [
            InkWell(
              onTap: () {
                setState(() {
                  _selectedProvider = null;
                  _testMessage = null;
                });
              },
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.arrow_back, size: 14, color: tokens.brand),
                  const SizedBox(width: 4),
                  Text(
                    'All providers',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: tokens.brand,
                    ),
                  ),
                ],
              ),
            ),
            const Spacer(),
            if (p.isRecommended ?? false)
              const DocuVerseBadge(text: 'Recommended', variant: DocuVerseBadgeVariant.info),
          ],
        ),
        const SizedBox(height: 12),

        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: tokens.cardRaised,
            borderRadius: BorderRadius.circular(tokens.radiusCard),
            border: Border.all(color: tokens.border),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Configuring ${p.name}',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: tokens.foreground,
                ),
              ),
              if (p.description.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  p.description,
                  style: TextStyle(fontSize: 12, color: tokens.foregroundMuted),
                ),
              ],
              if (p.notes.isNotEmpty) ...[
                const SizedBox(height: 4),
                Text(
                  p.notes,
                  style: TextStyle(fontSize: 11, color: tokens.foregroundSubtle),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: 16),

        // Fields
        DocuVerseInput(
          controller: _apiBaseController,
          label: 'API Base URL',
          placeholder: p.recommendedBaseUrl.isNotEmpty ? p.recommendedBaseUrl : 'http://localhost:1234/v1',
          hint: 'The OpenAI-compatible endpoint URL',
          isMono: true,
        ),
        const SizedBox(height: 12),

        DocuVerseInput(
          controller: _apiKeyController,
          label: 'API Key',
          placeholder: p.requiresKey ? 'Enter API Key...' : 'Optional / Not required',
          isPassword: true,
          hint: p.envKeys.isNotEmpty ? 'Environment variable: ${p.envKeys.join(", ")}' : null,
          isMono: true,
        ),
        const SizedBox(height: 12),

        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Model ID',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: tokens.foregroundMuted,
                  ),
                ),
                if (availableModels.isNotEmpty)
                  PopupMenuButton<String>(
                    tooltip: 'Pick from discovered models',
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2, horizontal: 4),
                      child: Text(
                        'Select model (${availableModels.length})',
                        style: TextStyle(fontSize: 11, color: tokens.brand, fontWeight: FontWeight.w500),
                      ),
                    ),
                    itemBuilder: (context) => availableModels
                        .map(
                          (m) => PopupMenuItem<String>(
                            value: m,
                            child: Text(m, style: const TextStyle(fontSize: 12, fontFamily: 'monospace')),
                          ),
                        )
                        .toList(),
                    onSelected: (model) {
                      _modelController.text = model;
                    },
                  ),
              ],
            ),
            const SizedBox(height: 6),
            DocuVerseInput(
              controller: _modelController,
              placeholder: 'e.g. allenai/olmocr-2-7b, gpt-4o, claude-3-5-sonnet',
              isMono: true,
            ),
          ],
        ),
        const SizedBox(height: 14),

        // Connection Test Result Badge / Box
        if (_testMessage != null) ...[
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: _testSuccess
                  ? tokens.success.withValues(alpha: 0.12)
                  : tokens.danger.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(
                color: _testSuccess
                    ? tokens.success.withValues(alpha: 0.35)
                    : tokens.danger.withValues(alpha: 0.35),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  _testSuccess ? Icons.check_circle_outline : Icons.error_outline,
                  size: 16,
                  color: _testSuccess ? tokens.success : tokens.danger,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    _testMessage!,
                    style: TextStyle(
                      fontSize: 12,
                      color: _testSuccess ? tokens.success : tokens.danger,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),
        ],

        // Action Buttons
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            DocuVerseButton(
              text: 'Test connection',
              variant: DocuVerseButtonVariant.secondary,
              loading: _isTesting,
              onPressed: _runConnectionTest,
              icon: const Icon(Icons.bolt, size: 14),
            ),
            Row(
              children: [
                DocuVerseButton(
                  text: 'Cancel',
                  variant: DocuVerseButtonVariant.ghost,
                  onPressed: () {
                    setState(() {
                      _selectedProvider = null;
                    });
                  },
                ),
                const SizedBox(width: 8),
                DocuVerseButton(
                  text: 'Apply as active',
                  variant: DocuVerseButtonVariant.primary,
                  loading: _isSaving,
                  onPressed: _applyProvider,
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}
