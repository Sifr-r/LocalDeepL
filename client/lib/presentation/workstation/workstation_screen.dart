import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/data/providers/workstation_state.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'canvas/bbox_inspector.dart';
import 'canvas/document_viewport.dart';
import 'controls/page_strip.dart';
import 'controls/right_control_dock.dart';
import 'controls/upload_dropzone.dart';
import 'modals/export_modal.dart';
import 'progress/bottom_progress_dock.dart';

/// Main OCR Workstation Screen uniting the GPU Document Viewport, BBox Inspector,
/// multi-page strip, controls dock, and real-time live progress dock.
class WorkstationScreen extends ConsumerStatefulWidget {
  const WorkstationScreen({super.key});

  @override
  ConsumerState<WorkstationScreen> createState() => _WorkstationScreenState();
}

class _WorkstationScreenState extends ConsumerState<WorkstationScreen> {
  ProcessSettings _processSettings = const ProcessSettings();

  /// Triggers document processing (Sync / Async OCR with Live streaming)
  Future<void> _handleProcessDocument(ProcessSettings settings) async {
    final wsState = ref.read(workstationProvider);
    if (!wsState.hasDocument) return;

    final notifier = ref.read(workstationProvider.notifier);
    if (settings.useAsync) {
      await notifier.processOcrAsync(settings: settings);
    } else {
      await notifier.processOcrSync(settings: settings);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final wsState = ref.watch(workstationProvider);
    final notifier = ref.read(workstationProvider.notifier);

    final hasDoc = wsState.hasDocument;
    final selectedBBox = wsState.selectedBBox;

    return Container(
      color: colors.background,
      child: Column(
        children: [
          // Main Workstation Header Bar
          _buildHeaderBar(context, colors, wsState, notifier),

          // Main Workstation Content Area
          Expanded(
            child: !hasDoc
                // 1. Empty state / Initial dropzone
                ? Center(
                    child: Container(
                      constraints: const BoxConstraints(maxWidth: 640),
                      padding: const EdgeInsets.all(24),
                      child: const UploadDropzone(),
                    ),
                  )
                // 2. Full Active Workstation Split-Pane
                : Padding(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final isWide = constraints.maxWidth >= 1080;

                        if (isWide) {
                          return Row(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              // Left/Center Area: Viewport + PageStrip + Inspector
                              Expanded(
                                flex: 8,
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.stretch,
                                children: [
                                  // Viewport + Side Inspector Split
                                  Expanded(
                                    child: Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        // Main Viewport
                                        Expanded(
                                          child: DocumentViewport(
                                            onBBoxSelected: (box) =>
                                                notifier.selectBBox(box),
                                          ),
                                        ),

                                        // Side BBox Inspector (if a box is selected)
                                        if (selectedBBox != null) ...[
                                          const SizedBox(width: 12),
                                          SizedBox(
                                            width: 320,
                                            child: BBoxInspector(
                                              bbox: selectedBBox,
                                              onClose: () =>
                                                  notifier.selectBBox(null),
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),

                                  // Multi-Page Strip (if doc has > 1 page)
                                  if (wsState.pageCount > 1) ...[
                                    const SizedBox(height: 12),
                                    const PageStrip(
                                        orientation: Axis.horizontal),
                                  ],
                                ],
                              ),
                            ),
                            const SizedBox(width: 16),

                            // Right Controls Dock
                            SizedBox(
                              width: 340,
                              child: RightControlDock(
                                settings: _processSettings,
                                onSettingsChanged: (s) =>
                                    setState(() => _processSettings = s),
                                onProcessRequested: _handleProcessDocument,
                              ),
                            ),
                          ],
                        );
                      } else {
                        // Stacked layout for smaller viewports
                        return SingleChildScrollView(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
                              SizedBox(
                                height: 520,
                                child: DocumentViewport(
                                  onBBoxSelected: (box) =>
                                      notifier.selectBBox(box),
                                ),
                              ),
                              if (selectedBBox != null) ...[
                                const SizedBox(height: 12),
                                BBoxInspector(
                                  bbox: selectedBBox,
                                  onClose: () => notifier.selectBBox(null),
                                ),
                              ],
                              if (wsState.pageCount > 1) ...[
                                const SizedBox(height: 12),
                                const PageStrip(
                                    orientation: Axis.horizontal),
                              ],
                              const SizedBox(height: 16),
                              RightControlDock(
                                settings: _processSettings,
                                onSettingsChanged: (s) =>
                                    setState(() => _processSettings = s),
                                onProcessRequested: _handleProcessDocument,
                              ),
                            ],
                          ),
                        );
                      }
                    },
                  ),
                ),
          ),

          // Live Bottom Progress Dock
          if (hasDoc || wsState.isProcessing) const BottomProgressDock(),
        ],
      ),
    );
  }

  Widget _buildHeaderBar(
    BuildContext context,
    AppColorScheme colors,
    WorkstationState wsState,
    WorkstationNotifier notifier,
  ) {
    return Container(
      height: 52,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: BoxDecoration(
        color: colors.card,
        border: Border(bottom: BorderSide(color: colors.border)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Document Filename / Status
          Flexible(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 30,
                  height: 30,
                  decoration: BoxDecoration(
                    color: colors.brand.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: colors.brand.withValues(alpha: 0.3)),
                  ),
                  child: Center(
                    child: Icon(Icons.document_scanner,
                        size: 16, color: colors.brand),
                  ),
                ),
                const SizedBox(width: 12),
                Flexible(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        wsState.hasDocument
                            ? ((wsState.filename != null && wsState.filename!.isNotEmpty) ? wsState.filename! : 'Active Document')
                            : 'OmniScribe',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.titleSmall(
                          color: colors.textPrimary,
                        ),
                      ),
                      Text(
                        wsState.hasDocument
                            ? '${wsState.pageCount} page${wsState.pageCount == 1 ? "" : "s"} • ${wsState.allBBoxes.length} bounding boxes'
                            : 'GPU-Accelerated Document Workstation',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: AppTypography.codeSmall(
                          color: colors.textMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Header Actions (Export, Clear, Status Badge)
          Row(
            children: [
              if (wsState.hasDocument) ...[
                AppButton(
                  text: 'Export',
                  variant: AppButtonVariant.secondary,
                  size: AppButtonSize.sm,
                  icon: const Icon(Icons.file_download_outlined, size: 14),
                  onPressed: () {
                    ExportModal.show(context);
                  },
                ),
                const SizedBox(width: 8),
                AppButton(
                  text: 'Clear Document',
                  variant: AppButtonVariant.ghost,
                  size: AppButtonSize.sm,
                  icon: const Icon(Icons.clear_all_rounded, size: 14),
                  onPressed: () {
                    notifier.clearDocument();
                  },
                ),
                const SizedBox(width: 8),
              ] else ...[
                const AppBadge(
                  label: 'DOCUVERSE 2.0',
                  variant: AppBadgeVariant.brand,
                  size: AppBadgeSize.sm,
                ),
                const SizedBox(width: 8),
              ],
              AppBadge(
                label: wsState.hasDocument ? 'LOADED' : 'READY',
                variant: wsState.hasDocument ? AppBadgeVariant.success : AppBadgeVariant.neutral,
                size: AppBadgeSize.sm,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
