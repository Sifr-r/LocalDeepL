import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';

/// Jobs and Batch Processing History View.
class JobsView extends ConsumerStatefulWidget {
  const JobsView({super.key});

  @override
  ConsumerState<JobsView> createState() => _JobsViewState();
}

class _JobsViewState extends ConsumerState<JobsView> {
  final List<Map<String, dynamic>> _jobs = [
    {
      'id': 'job-8921a',
      'filename': 'Q3_Financial_Audit_Report.pdf',
      'model': 'qwen2-vl-72b',
      'pipeline': 'Hybrid Grounded',
      'pages': '1-12',
      'duration': '4.2s',
      'timestamp': '2026-08-24 16:45:12',
      'status': 'complete',
    },
    {
      'id': 'job-8920f',
      'filename': 'Patent_Specification_EN.pdf',
      'model': 'llama-3.2-vision',
      'pipeline': 'Grounded VLM',
      'pages': '1-4',
      'duration': '1.8s',
      'timestamp': '2026-08-24 16:32:00',
      'status': 'complete',
    },
    {
      'id': 'job-8919b',
      'filename': 'Scanned_Receipt_Receipts_Aug.tiff',
      'model': 'qwen2-vl-72b',
      'pipeline': 'Hybrid Fast',
      'pages': '1',
      'duration': '0.9s',
      'timestamp': '2026-08-24 15:58:30',
      'status': 'complete',
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
                    'Job Execution History',
                    style: AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Audit log of OCR processing tasks, batch runs, and document artifact tokens.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppButton(
                text: 'Clear All Jobs',
                icon: const Icon(Icons.delete_sweep_outlined),
                variant: AppButtonVariant.danger,
                size: AppButtonSize.md,
                onPressed: () {
                  setState(() => _jobs.clear());
                  ref.read(toastProvider.notifier).info('Job history cleared');
                },
              ),
            ],
          ),
          const SizedBox(height: 20),

          AppCard(
            title: 'Completed Jobs',
            subtitle: '${_jobs.length} jobs recorded in current session',
            headerLeading: Icon(Icons.layers_outlined, size: 18, color: colors.brandAccent),
            padding: AppCardPadding.none,
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  color: colors.cardRaised,
                  child: Row(
                    children: [
                      Expanded(flex: 3, child: Text('FILENAME', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('JOB ID', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('MODEL', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('DURATION', style: AppTypography.micro(color: colors.textMuted))),
                      Expanded(flex: 2, child: Text('STATUS', style: AppTypography.micro(color: colors.textMuted))),
                      const SizedBox(width: 80, child: Text('ACTION', style: TextStyle(fontSize: 10))),
                    ],
                  ),
                ),
                Divider(height: 1, color: colors.border),

                if (_jobs.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(40),
                    child: Center(
                      child: Text(
                        'No job history recorded yet.',
                        style: AppTypography.bodyMedium(color: colors.textMuted),
                      ),
                    ),
                  )
                else
                  ...List.generate(_jobs.length, (index) {
                    final job = _jobs[index];
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      decoration: BoxDecoration(
                        color: index.isEven ? colors.card : colors.cardRaised.withValues(alpha: 0.3),
                        border: Border(bottom: BorderSide(color: colors.border, width: 0.5)),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            flex: 3,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(job['filename'] as String, style: AppTypography.captionStrong(color: colors.textPrimary)),
                                Text(job['timestamp'] as String, style: AppTypography.codeSmall(color: colors.textMuted)),
                              ],
                            ),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(job['id'] as String, style: AppTypography.codeSmall(color: colors.textSecondary)),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(job['model'] as String, style: AppTypography.bodySmall(color: colors.textSecondary)),
                          ),
                          Expanded(
                            flex: 2,
                            child: Text(job['duration'] as String, style: AppTypography.codeSmall(color: colors.textSecondary)),
                          ),
                          Expanded(
                            flex: 2,
                            child: AppBadge(
                              label: 'Completed',
                              variant: AppBadgeVariant.success,
                              size: AppBadgeSize.sm,
                              dot: true,
                            ),
                          ),
                          SizedBox(
                            width: 80,
                            child: AppButton(
                              text: 'View',
                              variant: AppButtonVariant.ghost,
                              size: AppButtonSize.sm,
                              icon: const Icon(Icons.open_in_new, size: 14),
                              onPressed: () {
                                ref.read(toastProvider.notifier).info('Opening artifacts for ${job["id"]}');
                              },
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
}
