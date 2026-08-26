import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_state.dart';
import 'package:omniscribe_client/data/providers/provider_notifier.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/providers/provider_modal.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_toggle.dart';

/// Settings & Configuration screen.
///
/// Migrated to the consolidated `settingsStateProvider` (`Notifier<SettingsState>`).
/// Slice 1 wires the General & Server tab. Subsequent slices (Provider Browser, Job
/// History, Translation / Transcription / Security) plug into the same provider.
class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  int _activeTabIndex = 0;
  bool _isSaving = false;
  String? _saveStatusMessage;

  late TextEditingController _serverUrlController;
  late TextEditingController _dpiController;
  late TextEditingController _concurrencyController;
  late TextEditingController _denseThresholdController;
  late TextEditingController _maxImageDimController;
  late TextEditingController _slidingWindowController;

  final List<String> _tabs = [
    'General & Server',
    'OCR Pipeline',
    'Translation & Voice',
    'Security & Auth',
  ];

  @override
  void initState() {
    super.initState();
    final settings = ref.read(settingsStateProvider);
    final config = settings.runtimeConfig;
    _serverUrlController = TextEditingController(text: settings.serverBaseUrl);
    _dpiController = TextEditingController(text: '${config?.dpi ?? 200}');
    _concurrencyController =
        TextEditingController(text: '${config?.concurrency ?? 4}');
    _denseThresholdController =
        TextEditingController(text: '${config?.denseThreshold ?? 10}');
    _maxImageDimController =
        TextEditingController(text: '${config?.maxImageDim ?? 2048}');
    _slidingWindowController =
        TextEditingController(text: '${config?.slidingWindowWords ?? 32}');
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    _dpiController.dispose();
    _concurrencyController.dispose();
    _denseThresholdController.dispose();
    _maxImageDimController.dispose();
    _slidingWindowController.dispose();
    super.dispose();
  }

  Future<void> _saveAllSettings() async {
    setState(() {
      _isSaving = true;
      _saveStatusMessage = null;
    });

    try {
      final notifier = ref.read(settingsStateProvider.notifier);
      final settings = ref.read(settingsStateProvider);
      final runtimeConfig = settings.runtimeConfig;
      if (runtimeConfig == null) {
        if (mounted) {
          setState(() {
            _isSaving = false;
            _saveStatusMessage =
                'No runtime config loaded yet — connect to a server first.';
          });
        }
        return;
      }

      // Build the request payload from the current RuntimeConfig (full picture)
      // plus any user-typed overrides from the text fields.
      final ProcessSettings payload =
          ProcessSettings.defaultSettings().copyWith(
        apiBase: _serverUrlController.text.trim().isEmpty
            ? runtimeConfig.apiBase
            : _serverUrlController.text.trim(),
        dpi: int.tryParse(_dpiController.text) ?? runtimeConfig.dpi,
        concurrency: int.tryParse(_concurrencyController.text) ??
            runtimeConfig.concurrency,
        denseThreshold: int.tryParse(_denseThresholdController.text) ??
            runtimeConfig.denseThreshold,
        maxImageDim: int.tryParse(_maxImageDimController.text) ??
            runtimeConfig.maxImageDim,
      );

      await notifier.updateOcr(payload);

      if (mounted) {
        setState(() {
          _isSaving = false;
          _saveStatusMessage = 'All configuration changes saved successfully.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isSaving = false;
          _saveStatusMessage = 'Error saving settings: $e';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsStateProvider);
    final providerState = ref.watch(providerBrowserProvider);
    final tokens = context.docuVerse;

    return Scaffold(
      backgroundColor: tokens.app,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1000),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Settings & Configuration',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: tokens.foreground,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Configure endpoints, pipeline parameters, inference providers, and limits',
                          style: TextStyle(
                              fontSize: 12, color: tokens.foregroundMuted),
                        ),
                      ],
                    ),
                    Row(
                      children: [
                        DocuVerseButton(
                          text: 'Browse providers',
                          variant: DocuVerseButtonVariant.secondary,
                          icon: const Icon(Icons.hub, size: 14),
                          onPressed: () => ProviderModal.show(context),
                        ),
                        const SizedBox(width: 8),
                        DocuVerseButton(
                          text: 'Save settings',
                          variant: DocuVerseButtonVariant.primary,
                          loading: _isSaving,
                          icon: const Icon(Icons.check, size: 14),
                          onPressed: _saveAllSettings,
                        ),
                      ],
                    ),
                  ],
                ),
                const SizedBox(height: 16),

                if (_saveStatusMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 10),
                    decoration: BoxDecoration(
                      color: tokens.success.withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(
                          color: tokens.success.withValues(alpha: 0.35)),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.check_circle,
                            size: 16, color: tokens.success),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _saveStatusMessage!,
                            style:
                                TextStyle(fontSize: 12, color: tokens.success),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                ],

                // Tabs
                Container(
                  decoration: BoxDecoration(
                    border: Border(bottom: BorderSide(color: tokens.border)),
                  ),
                  child: Row(
                    children: List.generate(_tabs.length, (index) {
                      final isSelected = _activeTabIndex == index;
                      return InkWell(
                        onTap: () => setState(() => _activeTabIndex = index),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 16, vertical: 10),
                          decoration: BoxDecoration(
                            border: Border(
                              bottom: BorderSide(
                                color: isSelected
                                    ? tokens.brand
                                    : Colors.transparent,
                                width: 2,
                              ),
                            ),
                          ),
                          child: Text(
                            _tabs[index],
                            style: TextStyle(
                              fontSize: 13,
                              fontWeight: isSelected
                                  ? FontWeight.w600
                                  : FontWeight.normal,
                              color: isSelected
                                  ? tokens.brand
                                  : tokens.foregroundMuted,
                            ),
                          ),
                        ),
                      );
                    }),
                  ),
                ),
                const SizedBox(height: 20),

                // Tab content
                if (_activeTabIndex == 0)
                  _buildGeneralServerTab(tokens, settings, providerState)
                else if (_activeTabIndex == 1)
                  _buildOcrPipelineTab(tokens, settings)
                else if (_activeTabIndex == 2)
                  _buildTranslationVoiceTab(tokens, settings)
                else if (_activeTabIndex == 3)
                  _buildSecurityAuthTab(tokens, settings),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildGeneralServerTab(
    DocuVerseThemeTokens tokens,
    SettingsState settings,
    dynamic providerState,
  ) {
    final config = settings.runtimeConfig;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DocuVerseCard(
          padding: DocuVerseCardPadding.lg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const DocuVerseSectionHeader(
                title: 'OmniScribe Backend Connection',
                description:
                    'Specify the HTTP endpoint where the OmniScribe Python server is listening.',
              ),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: DocuVerseInput(
                      controller: _serverUrlController,
                      label: 'Backend Base URL',
                      placeholder: 'http://127.0.0.1:8000',
                      isMono: true,
                    ),
                  ),
                  const SizedBox(width: 12),
                  DocuVerseButton(
                    text: 'Test connection',
                    variant: DocuVerseButtonVariant.secondary,
                    icon: const Icon(Icons.network_check, size: 14),
                    onPressed: () {
                      ref
                          .read(settingsStateProvider.notifier)
                          .setServerBaseUrl(_serverUrlController.text.trim());
                    },
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        DocuVerseCard(
          padding: DocuVerseCardPadding.lg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              DocuVerseSectionHeader(
                title: 'Active Inference Provider',
                description:
                    'Quick selector for currently active LLM backend provider.',
                action: DocuVerseButton(
                  text: 'Provider catalog',
                  variant: DocuVerseButtonVariant.ghost,
                  size: DocuVerseButtonSize.sm,
                  onPressed: () => ProviderModal.show(context),
                ),
              ),
              Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: tokens.cardRaised,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: tokens.border),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.memory, size: 20, color: tokens.brand),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  'Provider: ${settings.activeProviderId.toUpperCase()}',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: tokens.foreground,
                                  ),
                                ),
                                Text(
                                  'Endpoint: ${config?.apiBase ?? "—"} | Model: ${config?.model ?? "—"}',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontFamily: 'monospace',
                                    color: tokens.foregroundMuted,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ],
                            ),
                          ),
                          if (settings.isLoading) ...[
                            const SizedBox(width: 8),
                            const SizedBox(
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              DocuVerseToggle(
                label: 'Dark Mode Theme',
                description:
                    'Toggle between DocuVerse Obsidian Dark and Alabaster Light theme.',
                checked: settings.isDarkMode,
                onChanged: (val) => ref
                    .read(settingsStateProvider.notifier)
                    .toggleDarkMode(val),
              ),
              if (settings.error != null) ...[
                const SizedBox(height: 12),
                DocuVerseBadge(
                  text: 'Error: ${settings.error}',
                  variant: DocuVerseBadgeVariant.danger,
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildOcrPipelineTab(
      DocuVerseThemeTokens tokens, SettingsState settings) {
    final config = settings.runtimeConfig;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DocuVerseCard(
          padding: DocuVerseCardPadding.lg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const DocuVerseSectionHeader(
                title: 'OCR Parameters & Concurrency',
                description:
                    'Fine-tune rendering resolution, worker threads, and image constraints.',
              ),
              Row(
                children: [
                  Expanded(
                    child: DocuVerseInput(
                      controller: _dpiController,
                      label: 'Rendering DPI',
                      placeholder: '200',
                      hint: 'Default 200 DPI for balance of speed and clarity',
                      isMono: true,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: DocuVerseInput(
                      controller: _concurrencyController,
                      label: 'Worker Concurrency',
                      placeholder: '4',
                      hint: 'Simultaneous pages processed in parallel',
                      isMono: true,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Row(
                children: [
                  Expanded(
                    child: DocuVerseInput(
                      controller: _denseThresholdController,
                      label: 'Dense Mode Threshold',
                      placeholder: '10',
                      hint: 'Minimum block count to activate dense chunking',
                      isMono: true,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: DocuVerseInput(
                      controller: _maxImageDimController,
                      label: 'Max Image Dimension (px)',
                      placeholder: '2048',
                      hint:
                          'Caps page canvas size before sending to vision model',
                      isMono: true,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              DocuVerseToggle(
                label: 'Async Processing by Default',
                description:
                    'Queue background processing jobs (POST /api/process/async) instead of blocking requests.',
                checked: settings.useAsync,
                onChanged: (val) =>
                    ref.read(settingsStateProvider.notifier).setUseAsync(val),
              ),
              const SizedBox(height: 12),
              DocuVerseToggle(
                label: 'Dual Engine Cross-Validation',
                description:
                    'Compare secondary OCR outputs for higher precision.',
                checked: config?.dualEngine ?? false,
                onChanged: (_) {}, // Wired through updateOcr on save
              ),
              const SizedBox(height: 12),
              DocuVerseToggle(
                label: 'Self-Correction & Spelling Repair',
                description:
                    'Run automated lexical sanity checks on detected blocks.',
                checked: config?.selfCorrection ?? false,
                onChanged: (_) {}, // Wired through updateOcr on save
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTranslationVoiceTab(
      DocuVerseThemeTokens tokens, SettingsState settings) {
    final config = settings.runtimeConfig;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DocuVerseCard(
          padding: DocuVerseCardPadding.lg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const DocuVerseSectionHeader(
                title: 'Translation & Transcription',
                description:
                    'Cross-page context window and transcription defaults. Slice 4 will surface dedicated controls for each model.',
              ),
              const SizedBox(height: 12),
              DocuVerseToggle(
                label: 'Cross-Page Translation Context',
                description:
                    'Maintain translation continuity across page boundaries.',
                checked: config?.crossPage ?? false,
                onChanged: (_) {},
              ),
              const SizedBox(height: 12),
              DocuVerseInput(
                controller: _slidingWindowController,
                label: 'Sliding Window Words',
                placeholder: '32',
                hint: 'Word count shared between adjacent translation segments',
                isMono: true,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildSecurityAuthTab(
      DocuVerseThemeTokens tokens, SettingsState settings) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        DocuVerseCard(
          padding: DocuVerseCardPadding.lg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: const [
              DocuVerseSectionHeader(
                title: 'Security & Auth',
                description:
                    'Auth token management lands in slice 5 once the auth middleware plugin is rebuilt.',
              ),
              SizedBox(height: 12),
              DocuVerseBadge(
                text: 'Auth token UI deferred to slice 5',
                variant: DocuVerseBadgeVariant.neutral,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
