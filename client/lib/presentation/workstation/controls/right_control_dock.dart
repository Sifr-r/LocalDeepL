import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_select.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_slider.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_toggle.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'quality_repair_dock.dart';

/// Right-hand control dock holding OCR configuration, processor selectors,
/// image preprocessing, quality repair loop, and the primary execution CTA.
class RightControlDock extends ConsumerStatefulWidget {
  const RightControlDock({
    super.key,
    required this.settings,
    required this.onSettingsChanged,
    required this.onProcessRequested,
  });

  final ProcessSettings settings;
  final ValueChanged<ProcessSettings> onSettingsChanged;
  final Future<void> Function(ProcessSettings settings) onProcessRequested;

  @override
  ConsumerState<RightControlDock> createState() => _RightControlDockState();
}

class _RightControlDockState extends ConsumerState<RightControlDock> {
  bool _isAdvancedExpanded = false;

  void _toggleProcessor(String processorId) {
    final proc = DocumentProcessorName.tryFromString(processorId);
    if (proc == null) return;
    final current = widget.settings.documentProcessors;
    final updated = current.contains(proc)
        ? current.where((p) => p != proc).toList()
        : [...current, proc];
    widget.onSettingsChanged(
        widget.settings.copyWith(documentProcessors: updated));
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final wsState = ref.watch(workstationProvider);
    final s = widget.settings;

    final isProcessing = wsState.isProcessing;
    final hasDoc = wsState.hasDocument;

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Main Pipeline Card
          DocuVerseCard(
            variant: DocuVerseCardVariant.defaultCard,
            padding: DocuVerseCardPadding.md,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                DocuVerseSectionHeader(
                  title: 'Pipeline Configuration',
                  action: DocuVerseBadge(
                    text: s.pipelineMode.label,
                    variant: DocuVerseBadgeVariant.brand,
                    size: DocuVerseBadgeSize.sm,
                  ),
                ),

                // Pipeline Mode Selector
                DocuVerseSelect<PipelineMode>(
                  label: 'Pipeline Mode',
                  value: s.pipelineMode,
                  items: const [
                    DocuVerseSelectItem(
                      value: PipelineMode.hybrid,
                      label: 'Hybrid (OCR + VLM)',
                      subtitle:
                          'Combines grounded coordinates with multimodal reasoning',
                    ),
                    DocuVerseSelectItem(
                      value: PipelineMode.grounded,
                      label: 'Grounded BBox',
                      subtitle: 'Fast layout detection with bounding boxes',
                    ),
                    DocuVerseSelectItem(
                      value: PipelineMode.groundedNative,
                      label: 'Grounded Native',
                      subtitle: 'Direct model-native token grounding',
                    ),
                  ],
                  onChanged: (mode) {
                    if (mode != null) {
                      widget.onSettingsChanged(s.copyWith(pipelineMode: mode));
                    }
                  },
                ),
                const SizedBox(height: 12),

                // Dense Mode & Spellcheck Grid
                Row(
                  children: [
                    Expanded(
                      child: DocuVerseSelect<DenseMode>(
                        label: 'Dense Mode',
                        value: s.denseMode,
                        items: const [
                          DocuVerseSelectItem(
                              value: DenseMode.auto, label: 'Auto'),
                          DocuVerseSelectItem(value: DenseMode.on, label: 'On'),
                          DocuVerseSelectItem(
                              value: DenseMode.off, label: 'Off'),
                        ],
                        onChanged: (mode) {
                          if (mode != null) {
                            widget
                                .onSettingsChanged(s.copyWith(denseMode: mode));
                          }
                        },
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: DocuVerseSelect<SpellcheckMode>(
                        label: 'Spellcheck',
                        value: s.spellcheck,
                        items: const [
                          DocuVerseSelectItem(
                              value: SpellcheckMode.none, label: 'None'),
                          DocuVerseSelectItem(
                              value: SpellcheckMode.enUS,
                              label: 'English (US)'),
                          DocuVerseSelectItem(
                              value: SpellcheckMode.ar, label: 'Arabic'),
                          DocuVerseSelectItem(
                              value: SpellcheckMode.de, label: 'German'),
                          DocuVerseSelectItem(
                              value: SpellcheckMode.es, label: 'Spanish'),
                          DocuVerseSelectItem(
                              value: SpellcheckMode.fr, label: 'French'),
                        ],
                        onChanged: (mode) {
                          if (mode != null) {
                            widget.onSettingsChanged(
                                s.copyWith(spellcheck: mode));
                          }
                        },
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                // DPI & Concurrency Sliders
                DocuVerseSlider(
                  label: 'Raster DPI',
                  value: s.dpi.toDouble(),
                  min: 150,
                  max: 400,
                  divisions: 25,
                  valueLabel: '${s.dpi} DPI',
                  onChanged: (val) {
                    widget.onSettingsChanged(s.copyWith(dpi: val.round()));
                  },
                ),
                const SizedBox(height: 10),

                DocuVerseSlider(
                  label: 'Page Concurrency',
                  value: s.concurrency.toDouble(),
                  min: 1,
                  max: 16,
                  divisions: 15,
                  valueLabel: '${s.concurrency} workers',
                  onChanged: (val) {
                    widget.onSettingsChanged(
                        s.copyWith(concurrency: val.round()));
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Document Processors Card
          DocuVerseCard(
            variant: DocuVerseCardVariant.defaultCard,
            padding: DocuVerseCardPadding.md,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const DocuVerseSectionHeader(title: 'Document Processors'),
                Text(
                  'Select analyzers to enrich document structure and reading order:',
                  style: TextStyle(
                    fontFamily: DocuVerseTypography.fontBody,
                    fontSize: 11,
                    color: colors.foregroundMuted,
                  ),
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: DocumentProcessorInfo.all.map((info) {
                    final isSelected =
                        s.documentProcessors.any((p) => p.value == info.id);
                    return Tooltip(
                      message: info.description,
                      child: InkWell(
                        onTap: () => _toggleProcessor(info.id),
                        borderRadius:
                            BorderRadius.circular(colors.buttonRadius),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 150),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 10, vertical: 6),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? colors.brand.withValues(alpha: 0.15)
                                : colors.cardRaised,
                            borderRadius:
                                BorderRadius.circular(colors.buttonRadius),
                            border: Border.all(
                              color: isSelected
                                  ? colors.brand.withValues(alpha: 0.5)
                                  : colors.border,
                              width: 1.0,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (isSelected) ...[
                                Icon(Icons.check,
                                    size: 12, color: colors.brand),
                                const SizedBox(width: 4),
                              ],
                              Text(
                                info.label,
                                style: TextStyle(
                                  fontFamily: DocuVerseTypography.fontBody,
                                  fontSize: 11,
                                  fontWeight: isSelected
                                      ? FontWeight.w600
                                      : FontWeight.w500,
                                  color: isSelected
                                      ? colors.brand
                                      : colors.foregroundMuted,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
          const SizedBox(height: 12),

          // Quality Repair Loop Dock
          QualityRepairDock(
            settings: s,
            onSettingsChanged: widget.onSettingsChanged,
          ),
          const SizedBox(height: 12),

          // Advanced Image Preprocessing Accordion Card
          DocuVerseCard(
            variant: DocuVerseCardVariant.defaultCard,
            padding: DocuVerseCardPadding.sm,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                InkWell(
                  onTap: () => setState(
                      () => _isAdvancedExpanded = !_isAdvancedExpanded),
                  borderRadius: BorderRadius.circular(4),
                  child: Padding(
                    padding: const EdgeInsets.all(6),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            Icon(Icons.tune_rounded,
                                size: 14, color: colors.foregroundMuted),
                            const SizedBox(width: 6),
                            Text(
                              'IMAGE PREPROCESSING',
                              style: TextStyle(
                                fontFamily: DocuVerseTypography.fontBody,
                                fontSize: 11,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.6,
                                color: colors.foregroundMuted,
                              ),
                            ),
                          ],
                        ),
                        Icon(
                          _isAdvancedExpanded
                              ? Icons.expand_less_rounded
                              : Icons.expand_more_rounded,
                          size: 18,
                          color: colors.foregroundMuted,
                        ),
                      ],
                    ),
                  ),
                ),
                if (_isAdvancedExpanded) ...[
                  const SizedBox(height: 6),
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: colors.cardRaised,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Column(
                      children: [
                        DocuVerseToggle(
                          label: 'Orientation Detection',
                          checked: s.orientationDetection,
                          onChanged: (v) => widget.onSettingsChanged(
                              s.copyWith(orientationDetection: v)),
                        ),
                        DocuVerseToggle(
                          label: 'Deskew Image',
                          checked: s.deskew,
                          onChanged: (v) =>
                              widget.onSettingsChanged(s.copyWith(deskew: v)),
                        ),
                        DocuVerseToggle(
                          label: 'Denoise Image',
                          checked: s.denoise,
                          onChanged: (v) =>
                              widget.onSettingsChanged(s.copyWith(denoise: v)),
                        ),
                        DocuVerseToggle(
                          label: 'Normalize Contrast',
                          checked: s.normalizeContrast,
                          onChanged: (v) => widget.onSettingsChanged(
                              s.copyWith(normalizeContrast: v)),
                        ),
                        DocuVerseToggle(
                          label: 'Crop Cleanup',
                          checked: s.cropCleanup,
                          onChanged: (v) => widget
                              .onSettingsChanged(s.copyWith(cropCleanup: v)),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Primary Process Action CTA
          DocuVerseButton(
            text: isProcessing ? 'Processing Document...' : 'Process Document',
            variant: DocuVerseButtonVariant.primary,
            size: DocuVerseButtonSize.lg,
            fullWidth: true,
            icon: const Icon(Icons.bolt_rounded, size: 18),
            loading: isProcessing,
            disabled: !hasDoc && !isProcessing,
            onPressed: () => widget.onProcessRequested(s),
          ),
        ],
      ),
    );
  }
}
