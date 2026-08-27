import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_slider.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_toggle.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// Quality Repair Loop controls dock matching DocuVerse design system.
class QualityRepairDock extends ConsumerWidget {
  const QualityRepairDock({
    super.key,
    required this.settings,
    required this.onSettingsChanged,
  });

  final ProcessSettings settings;
  final ValueChanged<ProcessSettings> onSettingsChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.docuVerse;
    final wsState = ref.watch(workstationProvider);

    final isRepairEnabled = settings.qualityRepairEnabled;
    final target = settings.qualityTarget ?? 0.85;
    final maxRetries = settings.maxRetries;

    final repairedCount = wsState.repairedCount;
    final retriesAttempted = wsState.totalRetriesAttempted;
    final avgConf = wsState.avgConfidence;

    return DocuVerseCard(
      variant: DocuVerseCardVariant.raised,
      padding: DocuVerseCardPadding.md,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header with Loop Badge
          DocuVerseSectionHeader(
            title: 'Quality Repair Loop',
            action: DocuVerseBadge(
              text: isRepairEnabled ? 'ACTIVE' : 'OFF',
              variant: isRepairEnabled
                  ? DocuVerseBadgeVariant.revised
                  : DocuVerseBadgeVariant.neutral,
              size: DocuVerseBadgeSize.sm,
            ),
          ),

          // Enable Quality Repair Loop Switch
          DocuVerseToggle(
            label: 'Auto-Repair Low Confidence Blocks',
            description:
                'Iteratively prompts VLM to refine blocks falling below the target threshold.',
            checked: isRepairEnabled,
            onChanged: (enabled) {
              onSettingsChanged(
                  settings.copyWith(qualityRepairEnabled: enabled));
            },
          ),
          const SizedBox(height: 12),

          if (isRepairEnabled) ...[
            // Quality Target Threshold Slider (0.50 - 1.00)
            DocuVerseSlider(
              label: 'Quality Target Threshold',
              value: target,
              min: 0.50,
              max: 1.00,
              divisions: 50,
              valueLabel: '${(target * 100).round()}%',
              helperText:
                  'Blocks scoring below this confidence trigger self-correction retries.',
              onChanged: (val) {
                onSettingsChanged(settings.copyWith(qualityTarget: val));
              },
            ),
            const SizedBox(height: 12),

            // Max Retries Slider (1 - 5)
            DocuVerseSlider(
              label: 'Max Repair Retries',
              value: maxRetries.toDouble(),
              min: 1.0,
              max: 5.0,
              divisions: 4,
              valueLabel:
                  '$maxRetries ${maxRetries == 1 ? "retry" : "retries"}',
              helperText:
                  'Maximum re-prompts per degraded block before finalizing.',
              onChanged: (val) {
                onSettingsChanged(settings.copyWith(maxRetries: val.round()));
              },
            ),
            const SizedBox(height: 14),

            // Live Repair Performance Metrics (During / After Run)
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: colors.card,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: colors.border),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        'Loop Statistics',
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontBody,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: colors.foregroundMuted,
                        ),
                      ),
                      if (avgConf != null) ...[
                        Text(
                          'Avg Conf: ${(avgConf * 100).round()}%',
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontMono,
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                            color: avgConf >= target
                                ? colors.success
                                : colors.warning,
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: _MetricItem(
                          label: 'Repaired Blocks',
                          value: '$repairedCount',
                          valueColor: colors.revisedCyan,
                        ),
                      ),
                      Container(width: 1, height: 28, color: colors.border),
                      Expanded(
                        child: _MetricItem(
                          label: 'Retries Attempted',
                          value: '$retriesAttempted',
                          valueColor: colors.warning,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _MetricItem extends StatelessWidget {
  const _MetricItem({
    required this.label,
    required this.value,
    required this.valueColor,
  });

  final String label;
  final String value;
  final Color valueColor;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    return Column(
      children: [
        Text(
          value,
          style: TextStyle(
            fontFamily: DocuVerseTypography.fontMono,
            fontSize: 16,
            fontWeight: FontWeight.w700,
            color: valueColor,
          ),
        ),
        const SizedBox(height: 2),
        Text(
          label,
          style: TextStyle(
            fontFamily: DocuVerseTypography.fontBody,
            fontSize: 10,
            color: colors.foregroundMuted,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}
