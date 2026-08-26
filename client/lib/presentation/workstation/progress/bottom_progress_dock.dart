import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/job_progress_state.dart';
import 'package:omniscribe_client/state/progress_provider.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';

/// Live Bottom Progress Dock displaying the stage stepper, animated progress bar,
/// quality loop counters, and cancel controls.
class BottomProgressDock extends StatelessWidget {
  const BottomProgressDock({
    super.key,
    this.onCancelJob,
  });

  final VoidCallback? onCancelJob;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final progressState = ProgressProvider.of(context);
    final progressNotifier = ProgressProvider.notifierOf(context);

    final isProcessing = progressState.isProcessing;
    final stage = progressState.stage;
    final percent = progressState.percent;
    final percentInt = progressState.percentInt;
    final statusMsg = progressState.statusMessage;

    final processedBlocks = progressState.processedBlocks;
    final totalBlocks = progressState.totalBlocks;
    final retries = progressState.totalRetriesAttempted;
    final repaired = progressState.repairedCount;
    final avgConf = progressState.avgConfidence;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: colors.cardRaised,
        border: Border(top: BorderSide(color: colors.border, width: 1.0)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.15),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 1. Stage Stepper Row
          _buildStageStepper(colors, progressState),
          const SizedBox(height: 10),

          // 2. Animated Progress Bar & Percent
          Row(
            children: [
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: Stack(
                    children: [
                      Container(
                        height: 6,
                        color: colors.muted.withValues(alpha: 0.5),
                      ),
                      AnimatedFractionallySizedBox(
                        duration: const Duration(milliseconds: 300),
                        curve: Curves.easeOutCubic,
                        widthFactor: (percent / 100.0).clamp(0.0, 1.0),
                        child: Container(
                          height: 6,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(
                              colors: isProcessing
                                  ? [colors.brand, colors.info]
                                  : stage == 'Complete'
                                      ? [
                                          colors.success,
                                          const Color(0xFF10B981)
                                        ]
                                      : [colors.muted, colors.foregroundSubtle],
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 12),
              Text(
                '$percentInt%',
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontMono,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                  color: isProcessing
                      ? colors.brand
                      : stage == 'Complete'
                          ? colors.success
                          : colors.foregroundMuted,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),

          // 3. Live Metrics Row & Status Message & Cancel CTA
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              // Left: Status Message / Log Stream
              Expanded(
                child: Row(
                  children: [
                    if (isProcessing) ...[
                      SizedBox(
                        width: 12,
                        height: 12,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor:
                              AlwaysStoppedAnimation<Color>(colors.brand),
                        ),
                      ),
                      const SizedBox(width: 8),
                    ] else if (stage == 'Complete') ...[
                      Icon(Icons.check_circle, size: 14, color: colors.success),
                      const SizedBox(width: 6),
                    ],
                    Flexible(
                      child: Text(
                        statusMsg,
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontBody,
                          fontSize: 12,
                          color: colors.foregroundMuted,
                        ),
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              ),

              // Middle: Metrics Pills (Blocks, Retries, Repaired, Conf)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildMetricPill(
                    label: 'Blocks',
                    value:
                        '$processedBlocks${totalBlocks > 0 ? "/$totalBlocks" : ""}',
                    colors: colors,
                  ),
                  const SizedBox(width: 8),
                  _buildMetricPill(
                    label: 'Retries',
                    value: '$retries',
                    colors: colors,
                    highlightColor: retries > 0 ? colors.warning : null,
                  ),
                  const SizedBox(width: 8),
                  _buildMetricPill(
                    label: 'Repaired',
                    value: '$repaired',
                    colors: colors,
                    highlightColor: repaired > 0 ? colors.revisedCyan : null,
                  ),
                  if (avgConf != null) ...[
                    const SizedBox(width: 8),
                    _buildMetricPill(
                      label: 'Avg Conf',
                      value: '${(avgConf * 100).round()}%',
                      colors: colors,
                      highlightColor:
                          avgConf >= 0.85 ? colors.success : colors.warning,
                    ),
                  ],
                ],
              ),

              // Right: Cancel Button
              if (isProcessing) ...[
                const SizedBox(width: 16),
                DocuVerseButton(
                  text: 'Cancel',
                  variant: DocuVerseButtonVariant.danger,
                  size: DocuVerseButtonSize.sm,
                  icon: const Icon(Icons.stop_circle_outlined, size: 14),
                  onPressed: () {
                    progressNotifier.cancelJob();
                    onCancelJob?.call();
                  },
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildStageStepper(
      DocuVerseThemeTokens colors, JobProgressState state) {
    final stages = JobProgressState.pipelineStages;
    final currentIdx = state.currentStageIndex;
    final isDone = state.stage == 'Complete';

    return Row(
      children: List.generate(stages.length * 2 - 1, (i) {
        if (i.isOdd) {
          // Connector line
          final stageBefore = i ~/ 2;
          final isPast = isDone || (currentIdx > stageBefore);
          return Expanded(
            child: Container(
              height: 2,
              color:
                  isPast ? colors.brand : colors.muted.withValues(alpha: 0.4),
            ),
          );
        }

        final stageIdx = i ~/ 2;
        final stageName = stages[stageIdx];
        final isStageActive = !isDone && (currentIdx == stageIdx);
        final isStagePast = isDone || (currentIdx > stageIdx);

        Color nodeBg;
        Color nodeBorder;
        Widget nodeContent;

        if (isStagePast) {
          nodeBg = colors.brand;
          nodeBorder = colors.brand;
          nodeContent = const Icon(Icons.check, size: 10, color: Colors.white);
        } else if (isStageActive) {
          nodeBg = colors.brand.withValues(alpha: 0.2);
          nodeBorder = colors.brand;
          nodeContent = Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(
              color: colors.brand,
              shape: BoxShape.circle,
            ),
          );
        } else {
          nodeBg = colors.card;
          nodeBorder = colors.borderStrong;
          nodeContent = Container(
            width: 4,
            height: 4,
            decoration: BoxDecoration(
              color: colors.foregroundSubtle.withValues(alpha: 0.5),
              shape: BoxShape.circle,
            ),
          );
        }

        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 18,
              height: 18,
              decoration: BoxDecoration(
                color: nodeBg,
                shape: BoxShape.circle,
                border: Border.all(color: nodeBorder, width: 1.5),
              ),
              child: Center(child: nodeContent),
            ),
            const SizedBox(width: 4),
            Text(
              stageName,
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontBody,
                fontSize: 10,
                fontWeight: isStageActive ? FontWeight.w700 : FontWeight.w500,
                color: isStageActive
                    ? colors.brand
                    : isStagePast
                        ? colors.foreground
                        : colors.foregroundSubtle,
              ),
            ),
          ],
        );
      }),
    );
  }

  Widget _buildMetricPill({
    required String label,
    required String value,
    required DocuVerseThemeTokens colors,
    Color? highlightColor,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: colors.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '$label: ',
            style: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 10,
              color: colors.foregroundMuted,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontFamily: DocuVerseTypography.fontMono,
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: highlightColor ?? colors.foreground,
            ),
          ),
        ],
      ),
    );
  }
}
