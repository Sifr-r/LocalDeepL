import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/models/job.dart';
import 'package:omniscribe_client/state/jobs_provider.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_modal.dart';

class JobHistoryScreen extends ConsumerStatefulWidget {
  const JobHistoryScreen({super.key});

  @override
  ConsumerState<JobHistoryScreen> createState() => _JobHistoryScreenState();
}

class _JobHistoryScreenState extends ConsumerState<JobHistoryScreen> {
  String? _downloadingJobId;
  String? _statusBanner;

  @override
  void initState() {
    super.initState();
    Future.microtask(() => ref.read(jobsProvider.notifier).fetchJobs());
  }

  DocuVerseBadgeVariant _statusVariant(String status) {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'complete':
      case 'success':
        return DocuVerseBadgeVariant.success;
      case 'processing':
      case 'pending':
        return DocuVerseBadgeVariant.warning;
      case 'failed':
      case 'error':
        return DocuVerseBadgeVariant.danger;
      case 'cancelled':
        return DocuVerseBadgeVariant.neutral;
      default:
        return DocuVerseBadgeVariant.neutral;
    }
  }

  Future<void> _handleDownload(JobRecord job) async {
    setState(() {
      _downloadingJobId = job.id;
      _statusBanner = null;
    });

    try {
      final token = job.textArtifactToken ?? '';
      final bytes = await ref.read(jobsProvider.notifier).downloadResult(job.id, token);
      if (mounted) {
        setState(() {
          _statusBanner = 'Downloaded searchable PDF for ${job.filename} (${bytes.lengthInBytes} bytes)';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusBanner = 'Download error: $e';
        });
      }
    } finally {
      if (mounted) {
        setState(() {
          _downloadingJobId = null;
        });
      }
    }
  }

  Future<void> _handleCancel(String jobId) async {
    try {
      await ref.read(jobsProvider.notifier).cancelJob(jobId);
      if (mounted) {
        setState(() {
          _statusBanner = 'Job $jobId cancellation requested.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _statusBanner = 'Cancel error: $e';
        });
      }
    }
  }

  void _showClearConfirmDialog() {
    DocuVerseModal.show(
      context: context,
      title: 'Clear All Job History?',
      description: 'This will remove all job records and drop associated cached artifacts from the server.',
      maxWidth: 480,
      actions: [
        DocuVerseButton(
          text: 'Cancel',
          variant: DocuVerseButtonVariant.ghost,
          onPressed: () => Navigator.of(context).pop(),
        ),
        DocuVerseButton(
          text: 'Clear all jobs',
          variant: DocuVerseButtonVariant.danger,
          onPressed: () async {
            Navigator.of(context).pop();
            await ref.read(jobsProvider.notifier).clearJobs();
            if (mounted) {
              setState(() {
                _statusBanner = 'Job execution history cleared.';
              });
            }
          },
        ),
      ],
      child: Text(
        'This action is irreversible. All past OCR, translation, and extraction task logs will be wiped.',
        style: TextStyle(
          fontSize: 13,
          color: context.docuVerse.foregroundMuted,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final jobsState = ref.watch(jobsProvider);
    final tokens = context.docuVerse;

    return Scaffold(
      backgroundColor: tokens.app,
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header
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
                          'Job Execution History',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.bold,
                            color: tokens.foreground,
                            letterSpacing: -0.5,
                          ),
                        ),
                        const SizedBox(width: 10),
                        DocuVerseBadge(text: '${jobsState.jobs.length} jobs',
                          variant: DocuVerseBadgeVariant.brand,
                          hasDot: true,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Audit log of previous OCR, Translation, and Extraction pipeline tasks',
                      style: TextStyle(fontSize: 12, color: tokens.foregroundMuted),
                    ),
                  ],
                ),
                Row(
                  children: [
                    DocuVerseButton(
                      text: 'Refresh',
                      variant: DocuVerseButtonVariant.secondary,
                      loading: jobsState.isFetching,
                      icon: const Icon(Icons.refresh, size: 14),
                      onPressed: () => ref.read(jobsProvider.notifier).fetchJobs(),
                    ),
                    const SizedBox(width: 8),
                    DocuVerseButton(
                      text: 'Clear all',
                      variant: DocuVerseButtonVariant.danger,
                      disabled: jobsState.jobs.isEmpty,
                      icon: const Icon(Icons.delete_outline, size: 14),
                      onPressed: _showClearConfirmDialog,
                    ),
                  ],
                ),
              ],
            ),
            const SizedBox(height: 16),

            if (_statusBanner != null) ...[
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: _statusBanner!.contains('error')
                      ? tokens.danger.withValues(alpha: 0.12)
                      : tokens.info.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: _statusBanner!.contains('error')
                        ? tokens.danger.withValues(alpha: 0.35)
                        : tokens.info.withValues(alpha: 0.35),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      _statusBanner!.contains('error') ? Icons.error_outline : Icons.info_outline,
                      size: 16,
                      color: _statusBanner!.contains('error') ? tokens.danger : tokens.info,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        _statusBanner!,
                        style: TextStyle(
                          fontSize: 12,
                          color: _statusBanner!.contains('error') ? tokens.danger : tokens.info,
                          fontFamily: 'monospace',
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],

            // Main Jobs Table
            Expanded(
              child: DocuVerseCard(
                padding: DocuVerseCardPadding.none,
                child: jobsState.jobs.isEmpty
                    ? Center(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.history, size: 48, color: tokens.foregroundSubtle),
                            const SizedBox(height: 12),
                            Text(
                              jobsState.isFetching
                                  ? 'Loading job history…'
                                  : 'No historical OCR or translation jobs found.',
                              style: TextStyle(color: tokens.foregroundMuted, fontSize: 13),
                            ),
                          ],
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
                              DataColumn(label: Text('Job ID', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Status', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Filename', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Pipeline / Model', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Duration', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Failed Pages', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                              DataColumn(label: Text('Actions', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12))),
                            ],
                            rows: jobsState.jobs.map((job) {
                              final isDownloading = _downloadingJobId == job.id;
                              final isRunning = job.status.toLowerCase() == 'processing' ||
                                  job.status.toLowerCase() == 'pending';

                              return DataRow(
                                cells: [
                                  DataCell(
                                    Text(
                                      job.id.length > 8 ? '${job.id.substring(0, 8)}…' : job.id,
                                      style: TextStyle(
                                        fontFamily: 'monospace',
                                        fontSize: 12,
                                        fontWeight: FontWeight.w600,
                                        color: tokens.foreground,
                                      ),
                                    ),
                                  ),
                                  DataCell(
                                    DocuVerseBadge(text: job.status.toUpperCase(),
                                      variant: _statusVariant(job.status),
                                    ),
                                  ),
                                  DataCell(
                                    ConstrainedBox(
                                      constraints: const BoxConstraints(maxWidth: 160),
                                      child: Text(
                                        job.filename,
                                        style: TextStyle(fontSize: 12, color: tokens.foreground),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                    ),
                                  ),
                                  DataCell(
                                    Text(
                                      '${job.pipelineMode} / ${job.model}',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontFamily: 'monospace',
                                        color: tokens.foregroundMuted,
                                      ),
                                    ),
                                  ),
                                  DataCell(
                                    Text(
                                      job.durationS > 0 ? '${job.durationS.toStringAsFixed(1)}s' : '—',
                                      style: TextStyle(
                                        fontSize: 12,
                                        fontFamily: 'monospace',
                                        color: tokens.foregroundMuted,
                                      ),
                                    ),
                                  ),
                                  DataCell(
                                    job.failedPages.isNotEmpty
                                        ? DocuVerseBadge(text: 'Pages: ${job.failedPages.join(", ")}',
                                            variant: DocuVerseBadgeVariant.danger,
                                          )
                                        : Text('None', style: TextStyle(fontSize: 12, color: tokens.foregroundSubtle)),
                                  ),
                                  DataCell(
                                    Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        if (isRunning) ...[
                                          DocuVerseButton(
                                            text: 'Cancel',
                                            variant: DocuVerseButtonVariant.danger,
                                            size: DocuVerseButtonSize.sm,
                                            onPressed: () => _handleCancel(job.id),
                                          ),
                                        ] else ...[
                                          DocuVerseButton(
                                            text: 'PDF',
                                            variant: DocuVerseButtonVariant.ghost,
                                            size: DocuVerseButtonSize.sm,
                                            loading: isDownloading,
                                            icon: const Icon(Icons.download, size: 14),
                                            onPressed: () => _handleDownload(job),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),
                                ],
                              );
                            }).toList(),
                          ),
                        ),
                      ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
