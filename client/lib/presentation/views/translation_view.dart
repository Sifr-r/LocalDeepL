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
import 'package:omniscribe_client/presentation/common/toast_service.dart';

/// 2-Pane Translation Editor View.
class TranslationView extends ConsumerStatefulWidget {
  const TranslationView({super.key});

  @override
  ConsumerState<TranslationView> createState() => _TranslationViewState();
}

class _TranslationViewState extends ConsumerState<TranslationView> {
  String _sourceLang = 'auto';
  String _targetLang = 'ar';
  bool _dualTranslate = true;
  bool _useGlossary = true;
  bool _isTranslating = false;

  final TextEditingController _sourceController = TextEditingController(
    text: 'OmniScribe is a high-accuracy document intelligence and OCR suite engineered for enterprise workflows.',
  );
  final TextEditingController _targetController = TextEditingController(
    text: 'أومني سكرايب هو جناح ذكاء مستندات واستخراج نصوص عالي الدقة مصمم لسير العمل المؤسسي.',
  );

  @override
  void dispose() {
    _sourceController.dispose();
    _targetController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;

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
                    'Translation Workbench',
                    style: AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Neural document translation with glossary constraint injection and dual-engine synthesis.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppBadge(
                label: 'Sliding Window Active',
                variant: AppBadgeVariant.info,
                size: AppBadgeSize.md,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Controls Bar
          AppCard(
            variant: AppCardVariant.raised,
            padding: AppCardPadding.sm,
            child: Row(
              children: [
                Expanded(
                  child: AppSelect<String>(
                    label: 'Source Language',
                    value: _sourceLang,
                    items: const [
                      AppSelectItem(value: 'auto', label: 'Auto Detect Language'),
                      AppSelectItem(value: 'en', label: 'English (US)'),
                      AppSelectItem(value: 'ar', label: 'Arabic (العربية)'),
                      AppSelectItem(value: 'fr', label: 'French (Français)'),
                      AppSelectItem(value: 'de', label: 'German (Deutsch)'),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _sourceLang = v);
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Padding(
                  padding: const EdgeInsets.only(top: 20),
                  child: AppButton(
                    variant: AppButtonVariant.ghost,
                    size: AppButtonSize.sm,
                    icon: const Icon(Icons.swap_horiz, size: 18),
                    tooltip: 'Swap Languages',
                    onPressed: () {
                      final tmp = _sourceLang;
                      setState(() {
                        _sourceLang = _targetLang;
                        _targetLang = tmp == 'auto' ? 'en' : tmp;
                      });
                    },
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: AppSelect<String>(
                    label: 'Target Language',
                    value: _targetLang,
                    items: const [
                      AppSelectItem(value: 'ar', label: 'Arabic (العربية)'),
                      AppSelectItem(value: 'en', label: 'English (US)'),
                      AppSelectItem(value: 'fr', label: 'French (Français)'),
                      AppSelectItem(value: 'de', label: 'German (Deutsch)'),
                      AppSelectItem(value: 'es', label: 'Spanish (Español)'),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _targetLang = v);
                    },
                  ),
                ),
                const SizedBox(width: 16),
                Padding(
                  padding: const EdgeInsets.only(top: 18),
                  child: AppToggle(
                    label: 'Dual Translate',
                    value: _dualTranslate,
                    onChanged: (v) => setState(() => _dualTranslate = v),
                  ),
                ),
                const SizedBox(width: 16),
                Padding(
                  padding: const EdgeInsets.only(top: 18),
                  child: AppToggle(
                    label: 'Use Glossary',
                    value: _useGlossary,
                    onChanged: (v) => setState(() => _useGlossary = v),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // 2-Pane Editor Grid
          LayoutBuilder(
            builder: (context, constraints) {
              final isWide = constraints.maxWidth >= 900;
              final paneWidth = isWide ? (constraints.maxWidth - 20) / 2 : double.infinity;

              return Wrap(
                spacing: 20,
                runSpacing: 20,
                children: [
                  // Source Pane
                  SizedBox(
                    width: paneWidth,
                    child: AppCard(
                      title: 'Source Text',
                      subtitle: 'Extracted OCR or uploaded copy',
                      headerLeading: Icon(Icons.source_outlined, size: 16, color: colors.brandAccent),
                      footer: Row(
                        children: [
                          Text('14 words • 108 characters', style: AppTypography.codeSmall(color: colors.textMuted)),
                          const Spacer(),
                          AppButton(
                            text: 'Clear',
                            variant: AppButtonVariant.ghost,
                            size: AppButtonSize.sm,
                            onPressed: () => _sourceController.clear(),
                          ),
                        ],
                      ),
                      child: AppInput(
                        controller: _sourceController,
                        placeholder: 'Enter text to translate...',
                        maxLines: 12,
                        minLines: 8,
                      ),
                    ),
                  ),

                  // Target Pane
                  SizedBox(
                    width: paneWidth,
                    child: AppCard(
                      title: 'Target Translation',
                      subtitle: 'Synthesized result with formatting',
                      headerLeading: Icon(Icons.translate, size: 16, color: colors.success),
                      footer: Row(
                        children: [
                          AppBadge(
                            label: 'Terminology Matched (2)',
                            variant: AppBadgeVariant.success,
                            size: AppBadgeSize.sm,
                          ),
                          const Spacer(),
                          AppButton(
                            text: 'Copy',
                            icon: const Icon(Icons.copy, size: 14),
                            variant: AppButtonVariant.secondary,
                            size: AppButtonSize.sm,
                            onPressed: () {
                              ref.read(toastProvider.notifier).success('Translation copied to clipboard');
                            },
                          ),
                        ],
                      ),
                      child: AppInput(
                        controller: _targetController,
                        placeholder: 'Translation will appear here...',
                        maxLines: 12,
                        minLines: 8,
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 20),

          // Action CTA
          AppButton(
            text: _isTranslating ? 'Translating Content...' : 'Translate Document',
            icon: const Icon(Icons.bolt),
            variant: AppButtonVariant.primary,
            size: AppButtonSize.lg,
            loading: _isTranslating,
            onPressed: () {
              setState(() => _isTranslating = true);
              Future.delayed(const Duration(milliseconds: 1400), () {
                if (mounted) {
                  setState(() => _isTranslating = false);
                  ref.read(toastProvider.notifier).success('Translation completed');
                }
              });
            },
          ),
        ],
      ),
    );
  }
}
