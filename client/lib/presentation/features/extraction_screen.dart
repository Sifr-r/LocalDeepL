import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/features_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

class ExtractionScreen extends ConsumerStatefulWidget {
  const ExtractionScreen({super.key});

  @override
  ConsumerState<ExtractionScreen> createState() => _ExtractionScreenState();
}

class _ExtractionScreenState extends ConsumerState<ExtractionScreen> {
  late final TextEditingController _inputTextController;
  late final TextEditingController _customSchemaController;

  static const List<Map<String, String>> _templates = [
    {'id': 'invoice', 'label': 'Invoice'},
    {'id': 'resume', 'label': 'Resume'},
    {'id': 'academic', 'label': 'Academic'},
    {'id': 'table', 'label': 'Table Extraction'},
    {'id': 'custom', 'label': 'Custom Schema'},
  ];

  @override
  void initState() {
    super.initState();
    final extractionState = ref.read(extractionProvider);
    _inputTextController =
        TextEditingController(text: extractionState.inputText);
    _customSchemaController =
        TextEditingController(text: extractionState.customSchema);
  }

  @override
  void dispose() {
    _inputTextController.dispose();
    _customSchemaController.dispose();
    super.dispose();
  }

  Future<void> _handleExtract() async {
    final text = _inputTextController.text.trim();
    if (text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Please enter or paste input text to extract.'),
        ),
      );
      return;
    }

    final notifier = ref.read(extractionProvider.notifier);
    notifier.setInputText(text);
    notifier.setCustomSchema(_customSchemaController.text.trim());

    final config = ref.read(settingsStateProvider).runtimeConfig;
    await notifier.extract(
      model: config?.model,
      apiBase: config?.apiBase,
      apiKey: config?.apiKey,
    );
  }

  void _copyJson(dynamic extractedData) {
    if (extractedData != null) {
      final jsonStr =
          const JsonEncoder.withIndent('  ').convert(extractedData);
      unawaited(Clipboard.setData(ClipboardData(text: jsonStr)));
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('JSON data copied to clipboard.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(extractionProvider);
    final notifier = ref.read(extractionProvider.notifier);
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
                          'Structured Information Extraction',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: tokens.foreground,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(width: 10),
                        const DocuVerseBadge(
                          text: 'JSON Schema / AST',
                          variant: DocuVerseBadgeVariant.brand,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Extract strongly-typed entities, tables, invoices, and key-values from OCR document trees',
                      style: TextStyle(
                        fontSize: 12,
                        color: tokens.foregroundMuted,
                      ),
                    ),
                  ],
                ),
                // Template Segmented Control
                Container(
                  padding: const EdgeInsets.all(3),
                  decoration: BoxDecoration(
                    color: tokens.cardRaised,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: tokens.border),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: _templates.map((tpl) {
                      final isSelected = state.selectedTemplate == tpl['id'];
                      return InkWell(
                        onTap: () =>
                            notifier.setSelectedTemplate(tpl['id']!),
                        borderRadius: BorderRadius.circular(4),
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color:
                                isSelected ? tokens.card : Colors.transparent,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            tpl['label']!,
                            style: TextStyle(
                              fontSize: 12,
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
                    }).toList(),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Dual Pane: Input + Schema vs Extracted JSON
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Left Pane: Input Text & Custom Prompt
                  Expanded(
                    child: DocuVerseCard(
                      padding: DocuVerseCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          DocuVerseSectionHeader(
                            title: 'Input Text / Document Artifact',
                            description:
                                'Source text containing unstructured information',
                            action: _inputTextController.text.isNotEmpty
                                ? InkWell(
                                    onTap: () {
                                      _inputTextController.clear();
                                      notifier.clearInputText();
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
                              controller: _inputTextController,
                              maxLines: null,
                              expands: true,
                              onChanged: notifier.setInputText,
                              style: TextStyle(
                                fontSize: 13,
                                color: tokens.foreground,
                                fontFamily: 'monospace',
                              ),
                              decoration: InputDecoration(
                                hintText:
                                    'Paste invoice text, resume, receipt, or academic table here…',
                                hintStyle: TextStyle(
                                  fontSize: 13,
                                  color: tokens.foregroundSubtle,
                                ),
                                border: InputBorder.none,
                              ),
                            ),
                          ),
                          if (state.selectedTemplate == 'custom') ...[
                            const SizedBox(height: 12),
                            Divider(color: tokens.border, height: 1),
                            const SizedBox(height: 8),
                            Text(
                              'Custom JSON Schema Definition',
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: tokens.foregroundMuted,
                              ),
                            ),
                            const SizedBox(height: 6),
                            SizedBox(
                              height: 110,
                              child: TextField(
                                controller: _customSchemaController,
                                maxLines: null,
                                expands: true,
                                onChanged: notifier.setCustomSchema,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: tokens.success,
                                  fontFamily: 'monospace',
                                ),
                                decoration: InputDecoration(
                                  filled: true,
                                  fillColor: tokens.cardRaised,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(6),
                                    borderSide:
                                        BorderSide(color: tokens.border),
                                  ),
                                ),
                              ),
                            ),
                          ],
                          const SizedBox(height: 14),
                          DocuVerseButton(
                            text: state.isExtracting
                                ? 'Extracting…'
                                : 'Run Structured Extraction',
                            variant: DocuVerseButtonVariant.primary,
                            fullWidth: true,
                            loading: state.isExtracting,
                            icon: const Icon(Icons.auto_fix_high, size: 16),
                            onPressed: _handleExtract,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),

                  // Right Pane: Extracted JSON AST Output
                  Expanded(
                    child: DocuVerseCard(
                      padding: DocuVerseCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          DocuVerseSectionHeader(
                            title: 'Extracted Output AST',
                            description:
                                'Typed JSON structure validated against selected schema',
                            action: state.extractedData != null
                                ? DocuVerseButton(
                                    text: 'Copy JSON',
                                    variant: DocuVerseButtonVariant.ghost,
                                    size: DocuVerseButtonSize.sm,
                                    icon: const Icon(Icons.copy, size: 14),
                                    onPressed: () =>
                                        _copyJson(state.extractedData),
                                  )
                                : null,
                          ),
                          Expanded(
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: tokens.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: tokens.border),
                              ),
                              child: state.isExtracting
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
                                            'Parsing entities and validating against schema…',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: tokens.foregroundMuted,
                                            ),
                                          ),
                                        ],
                                      ),
                                    )
                                  : state.extractedData != null
                                      ? SingleChildScrollView(
                                          child: SelectableText(
                                            const JsonEncoder.withIndent('  ')
                                                .convert(state.extractedData),
                                            style: TextStyle(
                                              fontSize: 12.5,
                                              fontFamily: 'monospace',
                                              color: tokens.success,
                                              height: 1.4,
                                            ),
                                          ),
                                        )
                                      : Center(
                                          child: Text(
                                            'Extracted JSON output structure will appear here after extraction.',
                                            style: TextStyle(
                                              fontSize: 13,
                                              color: tokens.foregroundSubtle,
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
