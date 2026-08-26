import 'package:flutter/material.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/app_toggle.dart';
import 'package:omniscribe_client/presentation/common/section_header.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Workstation View: 3-column OCR & document intelligence layout.
class WorkstationView extends ConsumerStatefulWidget {
  const WorkstationView({super.key});

  @override
  ConsumerState<WorkstationView> createState() => _WorkstationViewState();
}

class _WorkstationViewState extends ConsumerState<WorkstationView> {
  String _selectedPipeline = 'hybrid';
  String _denseMode = 'auto';
  bool _deskew = true;
  bool _denoise = true;
  bool _selfCorrection = true;
  bool _dualEngine = false;
  bool _isProcessing = false;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // View Header
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Document Workstation',
                    style:
                        AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Multi-modal OCR, grounded bounding boxes, and document structure enrichment.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppBadge(
                label: 'GPU Accelerated',
                icon: const Icon(Icons.bolt, size: 12),
                variant: AppBadgeVariant.brand,
                size: AppBadgeSize.md,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // 3-Column Responsive Grid
          LayoutBuilder(
            builder: (context, constraints) {
              final isWide = constraints.maxWidth >= 1024;

              if (isWide) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Column 1: Settings Panel (300px)
                    SizedBox(
                      width: 320,
                      child: _buildPipelineSettings(colors),
                    ),
                    const SizedBox(width: 20),

                    // Column 2: Document Canvas / Dropzone (Flex)
                    Expanded(
                      flex: 6,
                      child: _buildDocumentCanvas(colors),
                    ),
                    const SizedBox(width: 20),

                    // Column 3: Trust & Metadata Summary (320px)
                    SizedBox(
                      width: 320,
                      child: _buildMetadataSummary(colors),
                    ),
                  ],
                );
              }

              // Stacked for narrow screens
              return Column(
                children: [
                  _buildDocumentCanvas(colors),
                  const SizedBox(height: 20),
                  _buildPipelineSettings(colors),
                  const SizedBox(height: 20),
                  _buildMetadataSummary(colors),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildPipelineSettings(AppColorScheme colors) {
    return AppCard(
      title: 'Pipeline Settings',
      subtitle: 'Execution knobs & filters',
      headerLeading: Icon(Icons.tune_rounded, size: 18, color: colors.brand),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          AppSelect<String>(
            label: 'Pipeline Mode',
            value: _selectedPipeline,
            items: const [
              AppSelectItem(value: 'hybrid', label: 'Hybrid (Fast + Grounded)'),
              AppSelectItem(value: 'grounded', label: 'Grounded BBox (VLM)'),
              AppSelectItem(value: 'grounded_native', label: 'Grounded Native'),
            ],
            onChanged: (val) {
              if (val != null) setState(() => _selectedPipeline = val);
            },
          ),
          const SizedBox(height: 14),
          AppSelect<String>(
            label: 'Dense Mode',
            value: _denseMode,
            items: const [
              AppSelectItem(value: 'auto', label: 'Auto (Detect Density)'),
              AppSelectItem(value: 'on', label: 'Force Dense'),
              AppSelectItem(value: 'off', label: 'Sparse Only'),
            ],
            onChanged: (val) {
              if (val != null) setState(() => _denseMode = val);
            },
          ),
          const SizedBox(height: 16),
          const SectionHeader(title: 'Image Preprocessing', showDivider: true),
          AppToggle(
            label: 'Deskew Image',
            subtitle: 'Correct camera tilt angles',
            value: _deskew,
            onChanged: (v) => setState(() => _deskew = v),
          ),
          const SizedBox(height: 6),
          AppToggle(
            label: 'Denoise & Clean',
            subtitle: 'Filter speckles and shadows',
            value: _denoise,
            onChanged: (v) => setState(() => _denoise = v),
          ),
          const SizedBox(height: 16),
          const SectionHeader(title: 'Quality Routing', showDivider: true),
          AppToggle(
            label: 'Self-Correction',
            subtitle: 'Multi-pass retry on low confidence',
            value: _selfCorrection,
            onChanged: (v) => setState(() => _selfCorrection = v),
          ),
          const SizedBox(height: 6),
          AppToggle(
            label: 'Dual Engine Arbitration',
            subtitle: 'Synthesize outputs with consensus',
            value: _dualEngine,
            onChanged: (v) => setState(() => _dualEngine = v),
          ),
          const SizedBox(height: 20),
          AppButton(
            text: _isProcessing ? 'Processing Document...' : 'Run OCR Pipeline',
            icon: const Icon(Icons.play_arrow_rounded),
            variant: AppButtonVariant.primary,
            size: AppButtonSize.lg,
            fullWidth: true,
            loading: _isProcessing,
            onPressed: () {
              setState(() => _isProcessing = true);
              ref
                  .read(toastProvider.notifier)
                  .info('OCR job queued for processing');
              Future.delayed(const Duration(seconds: 2), () {
                if (mounted) {
                  setState(() => _isProcessing = false);
                  ref
                      .read(toastProvider.notifier)
                      .success('Document OCR completed with 94.8% confidence');
                }
              });
            },
          ),
        ],
      ),
    );
  }

  Widget _buildDocumentCanvas(AppColorScheme colors) {
    return AppCard(
      height: 600,
      variant: AppCardVariant.defaultCard,
      padding: AppCardPadding.none,
      child: Stack(
        children: [
          // Canvas Background
          Container(
            color: colors.background,
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      color: colors.cardRaised,
                      shape: BoxShape.circle,
                      border: Border.all(color: colors.borderStrong, width: 1),
                    ),
                    child: Icon(
                      Icons.cloud_upload_outlined,
                      size: 32,
                      color: colors.brandAccent,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Drop PDF or Image files here',
                    style: AppTypography.titleLarge(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Supports PDF, PNG, JPEG, TIFF, WEBP up to 50MB',
                    style: AppTypography.bodySmall(color: colors.textMuted),
                  ),
                  const SizedBox(height: 20),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      AppButton(
                        text: 'Choose Local File',
                        icon: const Icon(Icons.folder_open_rounded),
                        variant: AppButtonVariant.secondary,
                        size: AppButtonSize.md,
                        onPressed: () {
                          ref
                              .read(toastProvider.notifier)
                              .info('File picker opened');
                        },
                      ),
                      const SizedBox(width: 10),
                      AppButton(
                        text: 'Load Sample Doc',
                        icon: const Icon(Icons.description_outlined),
                        variant: AppButtonVariant.outline,
                        size: AppButtonSize.md,
                        onPressed: () {
                          ref
                              .read(toastProvider.notifier)
                              .success('Sample invoice loaded');
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),

          // Canvas Toolbar Overlay
          Positioned(
            top: 14,
            right: 14,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              decoration: BoxDecoration(
                color: colors.cardRaised.withValues(alpha: 0.9),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: colors.border, width: 1),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  AppButton(
                    variant: AppButtonVariant.ghost,
                    size: AppButtonSize.sm,
                    icon: const Icon(Icons.zoom_in, size: 16),
                    tooltip: 'Zoom In',
                    onPressed: () {},
                  ),
                  AppButton(
                    variant: AppButtonVariant.ghost,
                    size: AppButtonSize.sm,
                    icon: const Icon(Icons.zoom_out, size: 16),
                    tooltip: 'Zoom Out',
                    onPressed: () {},
                  ),
                  AppButton(
                    variant: AppButtonVariant.ghost,
                    size: AppButtonSize.sm,
                    icon: const Icon(Icons.fit_screen, size: 16),
                    tooltip: 'Fit to Screen',
                    onPressed: () {},
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetadataSummary(AppColorScheme colors) {
    return AppCard(
      title: 'Trust & Confidence',
      subtitle: 'Grounding validation metrics',
      headerLeading:
          Icon(Icons.verified_outlined, size: 18, color: colors.success),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Confidence Indicator Score
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: colors.cardRaised,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: colors.border, width: 1),
            ),
            child: Row(
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'AVG CONFIDENCE',
                      style: AppTypography.micro(color: colors.textMuted),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '94.8%',
                      style: AppTypography.displaySmall(color: colors.success)
                          .copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                AppBadge(
                  label: 'HIGH TRUST',
                  variant: AppBadgeVariant.success,
                  size: AppBadgeSize.md,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          const SectionHeader(title: 'Structure Elements', showDivider: true),
          _buildMetricRow('Detected Blocks', '34 blocks', colors),
          _buildMetricRow('Tables Extracted', '2 tables', colors),
          _buildMetricRow('Reading Order', 'Linear Top-Down', colors),
          _buildMetricRow('Language', 'English (en-US)', colors),
          const SizedBox(height: 16),

          const SectionHeader(title: 'Export Actions', showDivider: true),
          Row(
            children: [
              Expanded(
                child: AppButton(
                  text: 'Export JSON',
                  icon: const Icon(Icons.code, size: 14),
                  variant: AppButtonVariant.secondary,
                  size: AppButtonSize.sm,
                  onPressed: () {
                    ref
                        .read(toastProvider.notifier)
                        .info('Exporting JSON artifact');
                  },
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: AppButton(
                  text: 'Markdown',
                  icon: const Icon(Icons.text_snippet_outlined, size: 14),
                  variant: AppButtonVariant.secondary,
                  size: AppButtonSize.sm,
                  onPressed: () {
                    ref
                        .read(toastProvider.notifier)
                        .info('Exporting Markdown artifact');
                  },
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricRow(String label, String value, AppColorScheme colors) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: AppTypography.bodySmall(color: colors.textMuted)),
          Text(
            value,
            style: AppTypography.captionStrong(color: colors.textPrimary),
          ),
        ],
      ),
    );
  }
}
