import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/models/translation.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/state/features_provider.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_toggle.dart';

class TranslationScreen extends ConsumerStatefulWidget {
  const TranslationScreen({super.key});

  @override
  ConsumerState<TranslationScreen> createState() => _TranslationScreenState();
}

class _TranslationScreenState extends ConsumerState<TranslationScreen> {
  late TextEditingController _sourceTextController;
  String _targetLanguage = 'French';
  String _selectedModel = '';
  bool _useNllb = false;
  bool _useTree = false;
  bool _isTranslating = false;
  String _translatedOutput = '';
  String? _asyncJobId;
  String? _asyncStatus;
  Timer? _pollingTimer;

  final List<String> _languages = [
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
    _sourceTextController = TextEditingController();
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
            content: Text('Please provide source text to translate.')),
      );
      return;
    }

    setState(() {
      _isTranslating = true;
      _translatedOutput = '';
      _asyncStatus = null;
    });

    final repo = ref.read(featuresRepositoryProvider);
    final config = ref.read(settingsStateProvider).runtimeConfig;

    try {
      if (_useNllb) {
        final res = await repo.translateNllb(
          text: text,
          targetLanguage: _targetLanguage,
        );
        setState(() {
          _translatedOutput = res.translatedText;
        });
      } else {
        final req = TranslationRequest(
          text: text,
          targetLanguage: _targetLanguage,
          model: _selectedModel.isNotEmpty
              ? _selectedModel
              : (config?.translationModel ?? config?.model),
          apiBase: config?.translationApiBase ?? config?.apiBase,
          apiKey: config?.translationApiKey ?? config?.apiKey,
          dualTranslate: config?.dualTranslate ?? false,
        );
        final res = await repo.translate(req);
        setState(() {
          _translatedOutput = res.translatedText;
        });
      }
    } catch (e) {
      setState(() {
        _translatedOutput = 'Translation failed: $e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isTranslating = false;
        });
      }
    }
  }

  Future<void> _handleAsyncTranslate() async {
    final text = _sourceTextController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Please provide source text for async translation.')),
      );
      return;
    }

    setState(() {
      _isTranslating = true;
      _translatedOutput = '';
      _asyncStatus = 'Queuing async translation job...';
    });

    final repo = ref.read(featuresRepositoryProvider);
    final config = ref.read(settingsStateProvider).runtimeConfig;

    try {
      final req = TranslationRequest(
        text: text,
        targetLanguage: _targetLanguage,
        model: _selectedModel.isNotEmpty
            ? _selectedModel
            : (config?.translationModel ?? config?.model),
        apiBase: config?.translationApiBase ?? config?.apiBase,
      );
      final res = await repo.translateAsync(req);

      setState(() {
        _asyncJobId = res.jobId;
        _asyncStatus = 'Job ${res.jobId} queued. Polling progress...';
      });

      _startPolling(res.jobId);
    } catch (e) {
      setState(() {
        _isTranslating = false;
        _asyncStatus = 'Async translation failed: $e';
      });
    }
  }

  void _startPolling(String jobId) {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 2), (timer) async {
      try {
        final repo = ref.read(featuresRepositoryProvider);
        final status = await repo.getTranslationStatus(jobId);

        if (status.state.toUpperCase() == 'SUCCESS') {
          timer.cancel();
          setState(() {
            _isTranslating = false;
            _translatedOutput =
                status.result?.toString() ?? 'Translation completed.';
            _asyncStatus = 'Completed.';
          });
        } else if (status.state.toUpperCase() == 'FAILURE' ||
            status.error != null) {
          timer.cancel();
          setState(() {
            _isTranslating = false;
            _asyncStatus =
                'Failed: ${status.detail ?? status.error ?? "Unknown error"}';
          });
        } else {
          setState(() {
            _asyncStatus =
                'Status: ${status.state} (${status.status ?? "in-flight"})';
          });
        }
      } catch (e) {
        timer.cancel();
        setState(() {
          _isTranslating = false;
          _asyncStatus = 'Polling error: $e';
        });
      }
    });
  }

  void _copyOutput() {
    if (_translatedOutput.isNotEmpty) {
      Clipboard.setData(ClipboardData(text: _translatedOutput));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Translated text copied to clipboard.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final configState = ref.watch(settingsStateProvider);
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
                          fontSize: 12, color: tokens.foregroundMuted),
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
                          value: _targetLanguage,
                          dropdownColor: tokens.card,
                          style:
                              TextStyle(fontSize: 13, color: tokens.foreground),
                          icon: Icon(Icons.arrow_drop_down,
                              color: tokens.foregroundMuted),
                          items: _languages
                              .map(
                                (lang) => DropdownMenuItem(
                                  value: lang,
                                  child: Text(lang),
                                ),
                              )
                              .toList(),
                          onChanged: (val) {
                            if (val != null)
                              setState(() => _targetLanguage = val);
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
                  DocuVerseToggle(
                    label: 'NLLB Fast Engine',
                    description: 'Direct Meta NLLB-200 offline translation',
                    checked: _useNllb,
                    onChanged: (val) => setState(() => _useNllb = val),
                  ),
                  const SizedBox(width: 32),
                  DocuVerseToggle(
                    label: 'Tree-Aware Translation',
                    description:
                        'Preserve hierarchical layout headers and tables',
                    checked: _useTree,
                    onChanged: (val) => setState(() => _useTree = val),
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
                                    onTap: () => setState(
                                        () => _sourceTextController.clear()),
                                    child: Text(
                                      'Clear',
                                      style: TextStyle(
                                          fontSize: 12, color: tokens.danger),
                                    ),
                                  )
                                : null,
                          ),
                          Expanded(
                            child: TextField(
                              controller: _sourceTextController,
                              maxLines: null,
                              expands: true,
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
                                    color: tokens.foregroundSubtle),
                                border: InputBorder.none,
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          Row(
                            children: [
                              Expanded(
                                child: DocuVerseButton(
                                  text: _isTranslating
                                      ? 'Translating…'
                                      : 'Translate (Sync)',
                                  variant: DocuVerseButtonVariant.primary,
                                  loading: _isTranslating,
                                  icon: const Icon(Icons.translate, size: 14),
                                  onPressed: _handleSyncTranslate,
                                ),
                              ),
                              const SizedBox(width: 8),
                              DocuVerseButton(
                                text: 'Async',
                                variant: DocuVerseButtonVariant.secondary,
                                disabled: _isTranslating,
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
                            title: 'Translated Output ($_targetLanguage)',
                            description:
                                'Neural output with domain terminology preserved',
                            action: _translatedOutput.isNotEmpty
                                ? DocuVerseButton(
                                    text: 'Copy',
                                    variant: DocuVerseButtonVariant.ghost,
                                    size: DocuVerseButtonSize.sm,
                                    icon: const Icon(Icons.copy, size: 14),
                                    onPressed: _copyOutput,
                                  )
                                : null,
                          ),
                          if (_asyncStatus != null) ...[
                            Container(
                              padding: const EdgeInsets.all(8),
                              margin: const EdgeInsets.only(bottom: 8),
                              decoration: BoxDecoration(
                                color: tokens.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: tokens.border),
                              ),
                              child: Text(
                                _asyncStatus!,
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
                              child: _isTranslating && _translatedOutput.isEmpty
                                  ? Center(
                                      child: Column(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          CircularProgressIndicator(
                                            valueColor:
                                                AlwaysStoppedAnimation<Color>(
                                                    tokens.brand),
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
                                        _translatedOutput.isNotEmpty
                                            ? _translatedOutput
                                            : 'Translated text output will appear here once translation is triggered.',
                                        style: TextStyle(
                                          fontSize: 13,
                                          fontFamily: 'monospace',
                                          color: _translatedOutput.isNotEmpty
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
