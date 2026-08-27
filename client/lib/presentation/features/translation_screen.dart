import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/features_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_toggle.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

class TranslationScreen extends ConsumerStatefulWidget {
  const TranslationScreen({super.key});

  @override
  ConsumerState<TranslationScreen> createState() => _TranslationScreenState();
}

class _TranslationScreenState extends ConsumerState<TranslationScreen> {
  late final TextEditingController _sourceTextController;
  bool _useTree = false;
  Timer? _pollingTimer;

  static const List<String> _languages = [
    'French',
    'Spanish',
    'German',
    'Italian',
    'Portuguese',
    'Japanese',
    'Chinese (Simplified)',
    'Korean',
    'Russian',
    'Arabic',
    'Dutch',
  ];

  @override
  void initState() {
    super.initState();
    final initialText = ref.read(translationProvider).sourceText;
    _sourceTextController = TextEditingController(text: initialText);
  }

  @override
  void dispose() {
    _pollingTimer?.cancel();
    _sourceTextController.dispose();
    super.dispose();
  }

  Future<void> _handleSyncTranslate() async {
    final text = _sourceTextController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please provide source text to translate.'),
        ),
      );
      return;
    }

    final notifier = ref.read(translationProvider.notifier);
    notifier.setSourceText(text);

    final config = ref.read(settingsStateProvider).runtimeConfig;
    await notifier.translate(
      apiBase: config?.translationApiBase ?? config?.apiBase,
      apiKey: config?.translationApiKey ?? config?.apiKey,
      fallbackModel: config?.translationModel ?? config?.model,
      dualTranslate: config?.dualTranslate ?? false,
    );
  }

  Future<void> _handleAsyncTranslate() async {
    final text = _sourceTextController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please provide source text for async translation.'),
        ),
      );
      return;
    }

    final notifier = ref.read(translationProvider.notifier);
    notifier.setSourceText(text);

    final config = ref.read(settingsStateProvider).runtimeConfig;
    final jobId = await notifier.translateAsync(
      apiBase: config?.translationApiBase ?? config?.apiBase,
      apiKey: config?.translationApiKey ?? config?.apiKey,
      fallbackModel: config?.translationModel ?? config?.model,
    );

    if (jobId != null) {
      _startPolling(jobId);
    }
  }

  void _startPolling(String jobId) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      final notifier = ref.read(translationProvider.notifier);
      await notifier.checkTranslationStatus(jobId);

      final state = ref.read(translationProvider);
      if (!state.isTranslating) {
        timer.cancel();
      }
    });
  }

  void _copyOutput(String translatedOutput) {
    if (translatedOutput.isNotEmpty) {
      unawaited(Clipboard.setData(ClipboardData(text: translatedOutput)));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Translated text copied to clipboard.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(translationProvider);
    final notifier = ref.read(translationProvider.notifier);
    final tokens = context.docuVerse;

    return Scaffold(
      backgroundColor: tokens.app,
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header Bar
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          'Neural Translation Engine',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: tokens.foreground,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(width: 10),
                        const DocuVerseBadge(
                          text: 'LangGraph / NLLB-200',
                          variant: DocuVerseBadgeVariant.brand,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Context-aware dual-engine translation with term preservation & sliding window',
                      style: TextStyle(
                        fontSize: 12,
                        color: tokens.foregroundMuted,
                      ),
                    ),
                  ],
                ),
                Row(
                  children: [
                    // Target Language Selector
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10),
                      decoration: BoxDecoration(
                        color: tokens.cardRaised,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: tokens.border),
                      ),
                      child: DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: state.targetLanguage,
                          dropdownColor: tokens.card,
                          style: TextStyle(
                            fontSize: 13,
                            color: tokens.foreground,
                          ),
                          icon: Icon(
                            Icons.arrow_drop_down,
                            color: tokens.foregroundMuted,
                          ),
                          items: _languages
                              .map(
                                (lang) => DropdownMenuItem(
                                  value: lang,
                                  child: Text(lang),
                                ),
                              )
                              .toList(),
                          onChanged: (val) {
                            if (val != null) {
                              notifier.setTargetLanguage(val);
                            }
                          },
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Options Bar
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              decoration: BoxDecoration(
                color: tokens.cardRaised,
                borderRadius: BorderRadius.circular(tokens.radiusCard),
                border: Border.all(color: tokens.border),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: DocuVerseToggle(
                      label: 'NLLB Fast Engine',
                      description: 'Direct Meta NLLB-200 offline translation',
                      checked: state.useNllb,
                      onChanged: notifier.setUseNllb,
                    ),
                  ),
                  const SizedBox(width: 32),
                  Expanded(
                    child: DocuVerseToggle(
                      label: 'Tree-Aware Translation',
                      description:
                          'Preserve hierarchical layout headers and tables',
                      checked: _useTree,
                      onChanged: (val) => setState(() => _useTree = val),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),

            // Dual Pane: Source vs Translated
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Left Pane: Source Text
                  Expanded(
                    child: DocuVerseCard(
                      padding: DocuVerseCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          DocuVerseSectionHeader(
                            title: 'Source Text',
                            description:
                                'Paste text or loaded document text artifact',
                            action: _sourceTextController.text.isNotEmpty
                                ? InkWell(
                                    onTap: () {
                                      _sourceTextController.clear();
                                      notifier.clearSourceText();
                                      setState(() {});
                                    },
                                    child: Text(
                                      'Clear',
                                      style: TextStyle(
                                        fontSize: 12,
                                        color: tokens.danger,
                                      ),
                                    ),
                                  )
                                : null,
                          ),
                          Expanded(
                            child: TextField(
                              controller: _sourceTextController,
                              maxLines: null,
                              expands: true,
                              onChanged: notifier.setSourceText,
                              style: TextStyle(
                                fontSize: 13,
                                color: tokens.foreground,
                                fontFamily: 'monospace',
                              ),
                              decoration: InputDecoration(
                                hintText:
                                    'Enter or paste source document text here…',
                                hintStyle: TextStyle(
                                  fontSize: 13,
                                  color: tokens.foregroundSubtle,
                                ),
                                border: InputBorder.none,
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: DocuVerseButton(
                                  text: state.isTranslating
                                      ? 'Translating…'
                                      : 'Translate (Sync)',
                                  variant: DocuVerseButtonVariant.primary,
                                  loading: state.isTranslating,
                                  icon: const Icon(Icons.translate, size: 14),
                                  onPressed: _handleSyncTranslate,
                                ),
                              ),
                              const SizedBox(width: 8),
                              DocuVerseButton(
                                text: 'Async',
                                variant: DocuVerseButtonVariant.secondary,
                                disabled: state.isTranslating,
                                tooltip:
                                    'Queue background task for large texts',
                                onPressed: _handleAsyncTranslate,
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),

                  // Right Pane: Translated Output
                  Expanded(
                    child: DocuVerseCard(
                      padding: DocuVerseCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          DocuVerseSectionHeader(
                            title:
                                'Translated Output (${state.targetLanguage})',
                            description:
                                'Neural output with domain terminology preserved',
                            action: state.translatedOutput.isNotEmpty
                                ? DocuVerseButton(
                                    text: 'Copy',
                                    variant: DocuVerseButtonVariant.ghost,
                                    size: DocuVerseButtonSize.sm,
                                    icon: const Icon(Icons.copy, size: 14),
                                    onPressed: () =>
                                        _copyOutput(state.translatedOutput),
                                  )
                                : null,
                          ),
                          if (state.asyncStatus != null) ...[
                            Container(
                              padding: const EdgeInsets.all(8),
                              margin: const EdgeInsets.only(bottom: 8),
                              decoration: BoxDecoration(
                                color: tokens.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: tokens.border),
                              ),
                              child: Text(
                                state.asyncStatus!,
                                style: TextStyle(
                                  fontSize: 11,
                                  fontFamily: 'monospace',
                                  color: tokens.foregroundMuted,
                                ),
                              ),
                            ),
                          ],
                          Expanded(
                            child: Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: tokens.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: tokens.border),
                              ),
                              child: state.isTranslating &&
                                      state.translatedOutput.isEmpty
                                  ? Center(
                                      child: Column(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          CircularProgressIndicator(
                                            valueColor:
                                                AlwaysStoppedAnimation<Color>(
                                              tokens.brand,
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          Text(
                                            'Translating document chunks…',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: tokens.foregroundMuted,
                                            ),
                                          ),
                                        ],
                                      ),
                                    )
                                  : SingleChildScrollView(
                                      child: SelectableText(
                                        state.translatedOutput.isNotEmpty
                                            ? state.translatedOutput
                                            : 'Translated text output will appear here once translation is triggered.',
                                        style: TextStyle(
                                          fontSize: 13,
                                          fontFamily: 'monospace',
                                          color:
                                              state.translatedOutput.isNotEmpty
                                                  ? tokens.foreground
                                                  : tokens.foregroundSubtle,
                                        ),
                                      ),
                                    ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
