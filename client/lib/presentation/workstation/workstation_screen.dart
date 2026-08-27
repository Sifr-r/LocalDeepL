import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/data/providers/workstation_state.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'canvas/bbox_inspector.dart';
import 'canvas/document_viewport.dart';
import 'controls/page_strip.dart';
import 'controls/right_control_dock.dart';
import 'controls/upload_dropzone.dart';
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
    final colors = context.docuVerse;
    final wsState = ref.watch(workstationProvider);
    final notifier = ref.read(workstationProvider.notifier);

    final hasDoc = wsState.hasDocument;
    final selectedBBox = wsState.selectedBBox;

    return Container(
      color: colors.app,
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
    DocuVerseThemeTokens colors,
    WorkstationState wsState,
    WorkstationNotifier notifier,
  ) {
    return Container(
      height: 56,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: BoxDecoration(
        color: colors.card,
        border: Border(bottom: BorderSide(color: colors.border)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // OmniScribe Brand & Title
          Flexible(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 32,
                  height: 32,
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [colors.brand, const Color(0xFF818CF8)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Center(
                    child: Icon(Icons.auto_stories_rounded,
                        size: 18, color: Colors.white),
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
                        'OmniScribe',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontDisplay,
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: colors.foreground,
                          height: 1.1,
                        ),
                      ),
                      Text(
                        'GPU-Accelerated Document Workstation',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontBody,
                          fontSize: 10,
                          color: colors.foregroundMuted,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // Header Actions (Clear, Load New, Help)
          Row(
            children: [
              if (wsState.hasDocument) ...[
                DocuVerseButton(
                  text: 'Clear Document',
                  variant: DocuVerseButtonVariant.ghost,
                  size: DocuVerseButtonSize.sm,
                  icon: const Icon(Icons.clear_all_rounded, size: 16),
                  onPressed: () {
                    notifier.clearDocument();
                  },
                ),
                const SizedBox(width: 8),
              ],
              const DocuVerseBadge(
                text: 'DOCUVERSE 2.0',
                variant: DocuVerseBadgeVariant.brand,
                size: DocuVerseBadgeSize.sm,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
