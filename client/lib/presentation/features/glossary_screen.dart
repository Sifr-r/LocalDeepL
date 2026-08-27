import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/feature_models.dart';
import 'package:omniscribe_client/data/providers/features_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_input.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_modal.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

class GlossaryScreen extends ConsumerStatefulWidget {
  const GlossaryScreen({super.key});

  @override
  ConsumerState<GlossaryScreen> createState() => _GlossaryScreenState();
}

class _GlossaryScreenState extends ConsumerState<GlossaryScreen> {
  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      final notifier = ref.read(glossaryProvider.notifier);
      unawaited(notifier.loadLibraries());
      unawaited(notifier.loadMergedLexicon());
    });
  }

  void _showImportModal() {
    final nameController = TextEditingController();
    final textController = TextEditingController();
    final urlController = TextEditingController();
    String formatValue = 'json_pairs';

    DocuVerseModal.show<void>(
      context: context,
      title: 'Import Terminology Glossary',
      description:
          'Upload a terminology file or import from a remote lexicon URL',
      maxWidth: 540,
      actions: [
        DocuVerseButton(
          text: 'Cancel',
          variant: DocuVerseButtonVariant.ghost,
          onPressed: () => Navigator.of(context).pop(),
        ),
        DocuVerseButton(
          text: 'Import Glossary',
          variant: DocuVerseButtonVariant.primary,
          onPressed: () async {
            final notifier = ref.read(glossaryProvider.notifier);
            final fmt = GlossaryFormat.fromString(formatValue);
            final urlText = urlController.text.trim();
            final nameText = nameController.text.trim();
            final contentText = textController.text.trim();

            if (urlText.isNotEmpty) {
              await notifier.importGlossaryUrl(
                url: urlText,
                format: fmt,
                name: nameText.isNotEmpty ? nameText : null,
              );
            } else {
              await notifier.importGlossaryJson(
                format: fmt,
                name: nameText.isNotEmpty ? nameText : null,
                text: contentText.isNotEmpty ? contentText : null,
              );
            }

            if (mounted) {
              Navigator.of(context).pop();
            }
          },
        ),
      ],
      child: StatefulBuilder(
        builder: (modalContext, setModalState) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              DocuVerseInput(
                controller: nameController,
                label: 'Glossary Name',
                placeholder: 'e.g. Financial Terms EN-ES',
              ),
              const SizedBox(height: 12),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Format',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: modalContext.docuVerse.foregroundMuted,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    decoration: BoxDecoration(
                      color: modalContext.docuVerse.cardRaised,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: modalContext.docuVerse.border),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        value: formatValue,
                        dropdownColor: modalContext.docuVerse.card,
                        style: TextStyle(
                          fontSize: 13,
                          color: modalContext.docuVerse.foreground,
                        ),
                        items: const [
                          DropdownMenuItem(
                            value: 'json_pairs',
                            child: Text('JSON Pairs / Paired Text'),
                          ),
                          DropdownMenuItem(
                            value: 'csv',
                            child: Text('CSV (Comma Separated)'),
                          ),
                          DropdownMenuItem(
                            value: 'tsv',
                            child: Text('TSV (Tab Separated)'),
                          ),
                          DropdownMenuItem(
                            value: 'tbx',
                            child: Text('TBX Glossary File'),
                          ),
                          DropdownMenuItem(
                            value: 'xliff',
                            child: Text('XLIFF Translation File'),
                          ),
                        ],
                        onChanged: (val) {
                          if (val != null) {
                            setModalState(() => formatValue = val);
                          }
                        },
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              DocuVerseInput(
                controller: textController,
                label: 'Inline Lexicon Content',
                placeholder: 'source = target\nplaintiff = demandeur',
                maxLines: 4,
                isMono: true,
              ),
              const SizedBox(height: 12),
              DocuVerseInput(
                controller: urlController,
                label: 'Or Import From URL',
                placeholder: 'https://example.com/lexicon.json',
                isMono: true,
              ),
            ],
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(glossaryProvider);
    final notifier = ref.read(glossaryProvider.notifier);
    final tokens = context.docuVerse;

    final activeCount = state.libraries.where((l) => l.enabled).length;

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
                          'Terminology Glossary',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: tokens.foreground,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(width: 10),
                        DocuVerseBadge(
                          text: '$activeCount active',
                          variant: DocuVerseBadgeVariant.success,
                          hasDot: true,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Manage domain lexicons, term overrides, and dictionary mappings',
                      style: TextStyle(
                        fontSize: 12,
                        color: tokens.foregroundMuted,
                      ),
                    ),
                  ],
                ),
                Row(
                  children: [
                    // Segmented Control
                    Container(
                      padding: const EdgeInsets.all(3),
                      decoration: BoxDecoration(
                        color: tokens.cardRaised,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: tokens.border),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          _buildTabButton(
                            'Libraries (${state.libraries.length})',
                            0,
                            state.activeViewIndex,
                            notifier,
                            tokens,
                          ),
                          _buildTabButton(
                            state.selectedLibrary != null
                                ? 'Entries (${state.entries.length})'
                                : 'Entries',
                            1,
                            state.activeViewIndex,
                            notifier,
                            tokens,
                          ),
                          _buildTabButton(
                            'Merged Lexicon (${state.mergedLexicon.length})',
                            2,
                            state.activeViewIndex,
                            notifier,
                            tokens,
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(width: 12),
                    DocuVerseButton(
                      text: 'Import glossary',
                      variant: DocuVerseButtonVariant.primary,
                      icon: const Icon(Icons.add, size: 14),
                      onPressed: _showImportModal,
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Views Content
            Expanded(
              child: state.activeViewIndex == 0
                  ? _buildLibrariesTable(state, notifier, tokens)
                  : (state.activeViewIndex == 1
                      ? _buildEntriesView(state, notifier, tokens)
                      : _buildMergedView(state, tokens)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTabButton(
    String label,
    int index,
    int activeViewIndex,
    GlossaryNotifier notifier,
    DocuVerseThemeTokens tokens,
  ) {
    final isSelected = activeViewIndex == index;
    return InkWell(
      onTap: () => notifier.setActiveViewIndex(index),
      borderRadius: BorderRadius.circular(4),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected ? tokens.card : Colors.transparent,
          borderRadius: BorderRadius.circular(4),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
            color: isSelected ? tokens.brand : tokens.foregroundMuted,
          ),
        ),
      ),
    );
  }

  Widget _buildLibrariesTable(
    GlossaryState state,
    GlossaryNotifier notifier,
    DocuVerseThemeTokens tokens,
  ) {
    return DocuVerseCard(
      padding: DocuVerseCardPadding.none,
      child: state.libraries.isEmpty
          ? Center(
              child: Text(
                'No glossary libraries imported yet. Click "Import glossary" to add terminology.',
                style: TextStyle(color: tokens.foregroundMuted, fontSize: 13),
              ),
            )
          : ClipRRect(
              borderRadius: BorderRadius.circular(tokens.radiusCard),
              child: SingleChildScrollView(
                child: DataTable(
                  headingRowColor: WidgetStateProperty.all(tokens.cardRaised),
                  dataRowColor: WidgetStateProperty.all(Colors.transparent),
                  dividerThickness: 1,
                  horizontalMargin: 16,
                  columnSpacing: 24,
                  columns: const [
                    DataColumn(
                      label: Text(
                        'Priority',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    DataColumn(
                      label: Text(
                        'Name',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    DataColumn(
                      label: Text(
                        'Format',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    DataColumn(
                      label: Text(
                        'Entries',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    DataColumn(
                      label: Text(
                        'Status',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                    DataColumn(
                      label: Text(
                        'Actions',
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                        ),
                      ),
                    ),
                  ],
                  rows: state.libraries.map((lib) {
                    return DataRow(
                      cells: [
                        DataCell(
                          Text(
                            '#${lib.priority}',
                            style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 12,
                              color: tokens.foregroundMuted,
                            ),
                          ),
                        ),
                        DataCell(
                          Text(
                            lib.name,
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 13,
                              color: tokens.brand,
                            ),
                          ),
                        ),
                        DataCell(
                          Text(
                            lib.format.value.toUpperCase(),
                            style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 11,
                              color: tokens.foregroundMuted,
                            ),
                          ),
                        ),
                        DataCell(
                          Text(
                            '${lib.entryCount}',
                            style: TextStyle(
                              fontFamily: 'monospace',
                              fontSize: 12,
                              color: tokens.foreground,
                            ),
                          ),
                        ),
                        DataCell(
                          DocuVerseBadge(
                            text: lib.enabled ? 'Enabled' : 'Disabled',
                            variant: lib.enabled
                                ? DocuVerseBadgeVariant.success
                                : DocuVerseBadgeVariant.neutral,
                            hasDot: lib.enabled,
                            onTap: () {
                              unawaited(notifier.toggleLibrary(lib, !lib.enabled));
                            },
                          ),
                        ),
                        DataCell(
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              DocuVerseButton(
                                text: 'View entries',
                                variant: DocuVerseButtonVariant.ghost,
                                size: DocuVerseButtonSize.sm,
                                onPressed: () {
                                  unawaited(notifier.loadEntries(lib));
                                },
                              ),
                              const SizedBox(width: 4),
                              DocuVerseButton(
                                text: 'Delete',
                                variant: DocuVerseButtonVariant.danger,
                                size: DocuVerseButtonSize.sm,
                                onPressed: () {
                                  unawaited(notifier.deleteLibrary(lib.id));
                                },
                              ),
                            ],
                          ),
                        ),
                      ],
                    );
                  }).toList(),
                ),
              ),
            ),
    );
  }

  Widget _buildEntriesView(
    GlossaryState state,
    GlossaryNotifier notifier,
    DocuVerseThemeTokens tokens,
  ) {
    return DocuVerseCard(
      padding: DocuVerseCardPadding.md,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          DocuVerseSectionHeader(
            title: state.selectedLibrary != null
                ? '${state.selectedLibrary!.name} (${state.entries.length} terms)'
                : 'Glossary Entries',
            description:
                'Source terms mapped to target domain translations with contextual notes',
            action: DocuVerseButton(
              text: 'Back to libraries',
              variant: DocuVerseButtonVariant.ghost,
              size: DocuVerseButtonSize.sm,
              onPressed: () => notifier.setActiveViewIndex(0),
            ),
          ),
          Expanded(
            child: state.entries.isEmpty
                ? Center(
                    child: Text(
                      'No terms found in this glossary library.',
                      style: TextStyle(
                        color: tokens.foregroundMuted,
                        fontSize: 13,
                      ),
                    ),
                  )
                : ListView.separated(
                    itemCount: state.entries.length,
                    separatorBuilder: (_, __) => const SizedBox(height: 6),
                    itemBuilder: (context, index) {
                      final entry = state.entries[index];
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: tokens.cardRaised,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: tokens.border),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              flex: 2,
                              child: Text(
                                entry.source,
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'monospace',
                                  color: tokens.foreground,
                                ),
                              ),
                            ),
                            Icon(
                              Icons.arrow_forward,
                              size: 14,
                              color: tokens.foregroundSubtle,
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              flex: 2,
                              child: Text(
                                entry.target,
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'monospace',
                                  color: tokens.brand,
                                ),
                              ),
                            ),
                            if (entry.note != null && entry.note!.isNotEmpty)
                              Expanded(
                                flex: 3,
                                child: Text(
                                  entry.note!,
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontStyle: FontStyle.italic,
                                    color: tokens.foregroundMuted,
                                  ),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildMergedView(
    GlossaryState state,
    DocuVerseThemeTokens tokens,
  ) {
    final entries = state.mergedLexicon.entries.toList();

    return DocuVerseCard(
      padding: DocuVerseCardPadding.md,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const DocuVerseSectionHeader(
            title: 'Merged Lexicon Table',
            description:
                'Combined active terms from all enabled libraries applied during OCR and translation',
          ),
          Expanded(
            child: entries.isEmpty
                ? Center(
                    child: Text(
                      'No active merged terms available.',
                      style: TextStyle(
                        color: tokens.foregroundMuted,
                        fontSize: 13,
                      ),
                    ),
                  )
                : GridView.builder(
                    gridDelegate:
                        const SliverGridDelegateWithMaxCrossAxisExtent(
                      maxCrossAxisExtent: 320,
                      mainAxisExtent: 44,
                      crossAxisSpacing: 10,
                      mainAxisSpacing: 10,
                    ),
                    itemCount: entries.length,
                    itemBuilder: (context, index) {
                      final item = entries[index];
                      return Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 10,
                          vertical: 6,
                        ),
                        decoration: BoxDecoration(
                          color: tokens.cardRaised,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: tokens.border),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Flexible(
                              child: Text(
                                item.key,
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'monospace',
                                  color: tokens.foreground,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Icon(
                              Icons.arrow_forward,
                              size: 12,
                              color: tokens.foregroundSubtle,
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                item.value,
                                style: TextStyle(
                                  fontSize: 12,
                                  fontWeight: FontWeight.w600,
                                  fontFamily: 'monospace',
                                  color: tokens.success,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
        ],
      ),
    );
  }
}
