import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/app_toggle.dart';
import 'package:omniscribe_client/presentation/common/section_header.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';
import 'package:omniscribe_client/presentation/shell/shell_state.dart';

/// Settings and Provider Configuration View.
class SettingsView extends ConsumerStatefulWidget {
  const SettingsView({super.key});

  @override
  ConsumerState<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends ConsumerState<SettingsView> {
  final TextEditingController _apiBaseCtrl = TextEditingController(text: 'http://localhost:11434/v1');
  final TextEditingController _apiKeyCtrl = TextEditingController(text: 'sk-ollama-local-token');
  final TextEditingController _ocrModelCtrl = TextEditingController(text: 'qwen2-vl-72b');
  final TextEditingController _transModelCtrl = TextEditingController(text: 'qwen2.5:72b');

  int _concurrency = 4;
  int _dpi = 300;
  bool _qualityRouting = true;
  bool _crossPage = true;
  bool _useAsync = true;

  @override
  void dispose() {
    _apiBaseCtrl.dispose();
    _apiKeyCtrl.dispose();
    _ocrModelCtrl.dispose();
    _transModelCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final activeProvider = ref.watch(activeProviderPresetProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'System Configuration',
                    style: AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'LLM inference endpoints, OCR concurrency limits, and image rasterization DPI.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppButton(
                text: 'Save Configurations',
                icon: const Icon(Icons.save_outlined),
                variant: AppButtonVariant.primary,
                size: AppButtonSize.md,
                onPressed: () {
                  ref.read(toastProvider.notifier).success('System settings saved successfully');
                },
              ),
            ],
          ),
          const SizedBox(height: 20),

          // 2-Pane Settings Grid
          LayoutBuilder(
            builder: (context, constraints) {
              final isWide = constraints.maxWidth >= 900;
              final paneWidth = isWide ? (constraints.maxWidth - 20) / 2 : double.infinity;

              return Wrap(
                spacing: 20,
                runSpacing: 20,
                children: [
                  // Pane 1: Provider Endpoints & Models
                  SizedBox(
                    width: paneWidth,
                    child: AppCard(
                      title: 'Inference Provider',
                      subtitle: 'LLM & VLM engine endpoints',
                      headerLeading: Icon(Icons.hub_outlined, size: 18, color: colors.brandAccent),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          AppSelect<String>(
                            label: 'Provider Preset',
                            value: activeProvider,
                            items: const [
                              AppSelectItem(value: 'Ollama (Local)', label: 'Ollama (Local GPU)'),
                              AppSelectItem(value: 'OpenAI (v1)', label: 'OpenAI API (GPT-4o / GPT-4o-mini)'),
                              AppSelectItem(value: 'Anthropic Claude', label: 'Anthropic Claude 3.5 Sonnet'),
                              AppSelectItem(value: 'vLLM Server', label: 'vLLM OpenAI-Compatible Server'),
                              AppSelectItem(value: 'Custom Endpoint', label: 'Custom Endpoint URL'),
                            ],
                            onChanged: (v) {
                              if (v != null) {
                                ref.read(activeProviderPresetProvider.notifier).state = v;
                                ref.read(toastProvider.notifier).info('Provider changed to $v');
                              }
                            },
                          ),
                          const SizedBox(height: 14),
                          AppInput(
                            controller: _apiBaseCtrl,
                            label: 'API Base URL',
                            placeholder: 'http://localhost:11434/v1',
                            helperText: 'OpenAI-compatible /v1 chat completions endpoint',
                          ),
                          const SizedBox(height: 14),
                          AppInput(
                            controller: _apiKeyCtrl,
                            label: 'API Key / Secret Token',
                            placeholder: 'Bearer token or API key',
                            obscureText: true,
                          ),
                          const SizedBox(height: 14),
                          AppInput(
                            controller: _ocrModelCtrl,
                            label: 'Default OCR Vision Model',
                            placeholder: 'qwen2-vl-72b',
                          ),
                          const SizedBox(height: 14),
                          AppInput(
                            controller: _transModelCtrl,
                            label: 'Default Translation Model',
                            placeholder: 'qwen2.5:72b',
                          ),
                        ],
                      ),
                    ),
                  ),

                  // Pane 2: Execution & Concurrency Limits
                  SizedBox(
                    width: paneWidth,
                    child: AppCard(
                      title: 'Performance & Concurrency',
                      subtitle: 'Parallel worker thresholds',
                      headerLeading: Icon(Icons.speed_outlined, size: 18, color: colors.cyan),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          AppSelect<int>(
                            label: 'Worker Concurrency (Threads)',
                            value: _concurrency,
                            items: const [
                              AppSelectItem(value: 1, label: '1 Worker (Sequential / Low Memory)'),
                              AppSelectItem(value: 2, label: '2 Workers (Balanced)'),
                              AppSelectItem(value: 4, label: '4 Workers (Recommended)'),
                              AppSelectItem(value: 8, label: '8 Workers (High Throughput GPU)'),
                            ],
                            onChanged: (v) {
                              if (v != null) setState(() => _concurrency = v);
                            },
                          ),
                          const SizedBox(height: 14),
                          AppSelect<int>(
                            label: 'PDF Rasterization DPI',
                            value: _dpi,
                            items: const [
                              AppSelectItem(value: 150, label: '150 DPI (Fast / Draft)'),
                              AppSelectItem(value: 200, label: '200 DPI (Standard)'),
                              AppSelectItem(value: 300, label: '300 DPI (High Precision - Recommended)'),
                              AppSelectItem(value: 400, label: '400 DPI (Ultra Fine Print / CJK / Arabic)'),
                            ],
                            onChanged: (v) {
                              if (v != null) setState(() => _dpi = v);
                            },
                          ),
                          const SizedBox(height: 16),
                          const SectionHeader(title: 'Advanced Flags', showDivider: true),
                          AppToggle(
                            label: 'Quality Routing & Arbitration',
                            subtitle: 'Enable confidence-weighted multi-pass processing',
                            value: _qualityRouting,
                            onChanged: (v) => setState(() => _qualityRouting = v),
                          ),
                          const SizedBox(height: 8),
                          AppToggle(
                            label: 'Cross-Page Context Window',
                            subtitle: 'Maintain translation continuity across page boundaries',
                            value: _crossPage,
                            onChanged: (v) => setState(() => _crossPage = v),
                          ),
                          const SizedBox(height: 8),
                          AppToggle(
                            label: 'Asynchronous Job Submissions',
                            subtitle: 'Poll for background job completions',
                            value: _useAsync,
                            onChanged: (v) => setState(() => _useAsync = v),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }
}
