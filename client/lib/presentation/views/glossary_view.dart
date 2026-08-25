import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_modal.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';

/// Glossary and Terminology Management View.
class GlossaryView extends ConsumerStatefulWidget {
  const GlossaryView({super.key});

  @override
  ConsumerState<GlossaryView> createState() => _GlossaryViewState();
}

class _GlossaryViewState extends ConsumerState<GlossaryView> {
  final List<Map<String, dynamic>> _glossaries = [
    {
      'id': 'gloss-01',
      'name': 'Medical & Clinical Terminology',
      'format': 'TBX',
      'entries': 1420,
      'enabled': true,
      'group': 'Healthcare',
    },
    {
      'id': 'gloss-02',
      'name': 'Legal Contracts & Agreements',
      'format': 'XLIFF',
      'entries': 850,
      'enabled': true,
      'group': 'Legal',
    },
    {
      'id': 'gloss-03',
      'name': 'IT & Cloud Infrastructure Pairs',
      'format': 'CSV',
      'entries': 3240,
      'enabled': false,
      'group': 'Engineering',
    },
  ];

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
                    'Glossary & Translation Memories',
                    style: AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Domain dictionaries, bilingual term pairs, and memory repositories (CSV, TSV, XLIFF, TBX, TMX).',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppButton(
                text: 'Import Glossary',
                icon: const Icon(Icons.add_rounded),
                variant: AppButtonVariant.primary,
                size: AppButtonSize.md,
                onPressed: () => _openImportModal(context),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Glossary Items Table Card
          AppCard(
            title: 'Active Glossaries',
            subtitle: '${_glossaries.length} glossaries loaded in workspace',
            headerLeading: Icon(Icons.auto_stories_outlined, size: 18, color: colors.brandAccent),
            padding: AppCardPadding.none,
            child: Column(
              children: [
                // Table Header
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  color: colors.cardRaised,
                  child: Row(
                    children: [
                      Expanded(flex: 4, child: Text('NAME', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('FORMAT', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('ENTRIES', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('GROUP', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('STATUS', style: AppTypography.micro(color: colors.textMuted))),
                      const SizedBox(width: 80, child: Text('ACTIONS', style: TextStyle(fontSize: 10))),
                    ],
                  ),
                ),
                Divider(height: 1, color: colors.border),

                // Table Rows
                ...List.generate(_glossaries.length, (index) {
                  final item = _glossaries[index];
                  final isEnabled = item['enabled'] as bool;

                  return Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    decoration: BoxDecoration(
                      color: index.isEven ? colors.card : colors.cardRaised.withValues(alpha: 0.3),
                      border: Border(bottom: BorderSide(color: colors.border, width: 0.5)),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          flex: 4,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(item['name'] as String, style: AppTypography.captionStrong(color: colors.textPrimary)),
                              Text(item['id'] as String, style: AppTypography.codeSmall(color: colors.textMuted)),
                            ],
                          ),
                        ),
                        Expanded(
                          flex: 2,
                          child: AppBadge(
                            label: item['format'] as String,
                            variant: AppBadgeVariant.neutral,
                            size: AppBadgeSize.sm,
                          ),
                        ),
                        Expanded(
                          flex: 2,
                          child: Text('${item['entries']} terms', style: AppTypography.bodySmall(color: colors.textSecondary)),
                        ),
                        Expanded(
                          flex: 2,
                          child: Text(item['group'] as String, style: AppTypography.bodySmall(color: colors.textSecondary)),
                        ),
                        Expanded(
                          flex: 2,
                          child: AppBadge(
                            label: isEnabled ? 'Active' : 'Disabled',
                            variant: isEnabled ? AppBadgeVariant.success : AppBadgeVariant.neutral,
                            size: AppBadgeSize.sm,
                            dot: true,
                          ),
                        ),
                        SizedBox(
                          width: 80,
                          child: Row(
                            children: [
                              AppButton(
                                variant: AppButtonVariant.ghost,
                                size: AppButtonSize.sm,
                                icon: Icon(isEnabled ? Icons.toggle_on : Icons.toggle_off, size: 20, color: isEnabled ? colors.brand : colors.textMuted),
                                tooltip: isEnabled ? 'Disable' : 'Enable',
                                onPressed: () {
                                  setState(() {
                                    item['enabled'] = !isEnabled;
                                  });
                                  ref.read(toastProvider.notifier).info(
                                    '${item['name']} ${!isEnabled ? "enabled" : "disabled"}',
                                  );
                                },
                              ),
                              AppButton(
                                variant: AppButtonVariant.ghost,
                                size: AppButtonSize.sm,
                                icon: Icon(Icons.delete_outline, size: 16, color: colors.error),
                                tooltip: 'Delete',
                                onPressed: () {
                                  setState(() {
                                    _glossaries.removeAt(index);
                                  });
                                  ref.read(toastProvider.notifier).warning('Glossary removed');
                                },
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _openImportModal(BuildContext context) {
    String format = 'csv';
    final nameCtrl = TextEditingController();

    AppModal.show<void>(
      context: context,
      title: 'Import Terminology Glossary',
      subtitle: 'Upload glossary file or connect remote Git/SQL table',
      icon: const Icon(Icons.file_upload_outlined),
      content: StatefulBuilder(
        builder: (ctx, setModalState) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AppInput(
                controller: nameCtrl,
                label: 'Glossary Name',
                placeholder: 'e.g. Legal Terminology 2026',
                isRequired: true,
              ),
              const SizedBox(height: 14),
              AppSelect<String>(
                label: 'Format',
                value: format,
                items: const [
                  AppSelectItem(value: 'csv', label: 'CSV (Comma Separated)'),
                  AppSelectItem(value: 'tsv', label: 'TSV (Tab Separated)'),
                  AppSelectItem(value: 'xliff', label: 'XLIFF (XML Localization)'),
                  AppSelectItem(value: 'tbx', label: 'TBX (TermBase eXchange)'),
                  AppSelectItem(value: 'tmx', label: 'TMX (Translation Memory)'),
                  AppSelectItem(value: 'json_pairs', label: 'JSON Key-Value Pairs'),
                ],
                onChanged: (v) {
                  if (v != null) setModalState(() => format = v);
                },
              ),
              const SizedBox(height: 14),
              const AppInput(
                label: 'File Path or URL',
                placeholder: 'https:// or local path',
              ),
            ],
          );
        },
      ),
      actions: [
        AppButton(
          text: 'Cancel',
          variant: AppButtonVariant.ghost,
          onPressed: () => Navigator.of(context).pop(),
        ),
        AppButton(
          text: 'Import File',
          variant: AppButtonVariant.primary,
          onPressed: () {
            Navigator.of(context).pop();
            setState(() {
              _glossaries.add({
                'id': 'gloss-0${_glossaries.length + 1}',
                'name': nameCtrl.text.isNotEmpty ? nameCtrl.text : 'Imported Glossary',
                'format': format.toUpperCase(),
                'entries': 120,
                'enabled': true,
                'group': 'General',
              });
            });
            ref.read(toastProvider.notifier).success('Glossary imported successfully');
          },
        ),
      ],
    );
  }
}
