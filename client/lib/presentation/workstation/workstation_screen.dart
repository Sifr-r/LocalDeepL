import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/models/document_view_model.dart';
import 'package:omniscribe_client/models/job_progress_state.dart';
import 'package:omniscribe_client/models/process_settings.dart';
import 'package:omniscribe_client/models/ws_envelope.dart';
import 'package:omniscribe_client/state/document_provider.dart';
import 'package:omniscribe_client/state/document_state.dart';
import 'package:omniscribe_client/state/progress_provider.dart';
import 'package:omniscribe_client/state/progress_state.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'canvas/bbox_inspector.dart';
import 'canvas/document_viewport.dart';
import 'controls/page_strip.dart';
import 'controls/right_control_dock.dart';
import 'controls/upload_dropzone.dart';
import 'progress/bottom_progress_dock.dart';

/// Main OCR Workstation Screen uniting the GPU Document Viewport, BBox Inspector,
/// multi-page strip, controls dock, and real-time live progress dock.
class WorkstationScreen extends StatefulWidget {
  const WorkstationScreen({super.key});

  @override
  State<WorkstationScreen> createState() => _WorkstationScreenState();
}

class _WorkstationScreenState extends State<WorkstationScreen> {
  late final DocumentStateNotifier _documentNotifier;
  late final ProgressStateNotifier _progressNotifier;

  ProcessSettings _processSettings = const ProcessSettings();
  Timer? _simulationTimer;

  @override
  void initState() {
    super.initState();
    _documentNotifier = DocumentStateNotifier();
    _progressNotifier = ProgressStateNotifier();

    // Hook progress notifier streamed bboxes directly into document notifier
    _progressNotifier.onBBoxStreamed = (page, bbox) {
      _documentNotifier.addOrUpdateBBox(page, bbox);
    };
  }

  @override
  void dispose() {
    _simulationTimer?.cancel();
    _documentNotifier.dispose();
    _progressNotifier.dispose();
    super.dispose();
  }

  /// Triggers document processing (Sync / Async OCR with Live streaming)
  Future<void> _handleProcessDocument(ProcessSettings settings) async {
    final docState = _documentNotifier.state;
    if (!docState.hasDocument) return;

    final jobId = 'job_${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
    final channelId = 'ws_$jobId';

    _progressNotifier.startJob(jobId, channelId);

    // Run simulated OCR pipeline sequence if offline or local demo
    _simulateOcrPipeline(docState, settings, jobId);
  }

  /// High-fidelity pipeline simulation demonstrating frames, bounding boxes, and quality loop
  void _simulateOcrPipeline(DocumentViewModel docState, ProcessSettings settings, String jobId) {
    _simulationTimer?.cancel();

    final pageCount = math.max(1, docState.pageCount);
    int step = 0;

    final sampleBoxesPerPage = [
      // Sample blocks for demo
      [
        const BBoxItem(
          blockId: 'p0_b0',
          page: 0,
          block: 0,
          bbox: [0.10, 0.08, 0.90, 0.16],
          text: 'OmniScribe GPU Document OCR Report',
          kind: 'title',
          confidence: 0.98,
        ),
        const BBoxItem(
          blockId: 'p0_b1',
          page: 0,
          block: 1,
          bbox: [0.10, 0.18, 0.90, 0.32],
          text: 'This workstation provides sub-second document grounding with multi-threaded token extraction and real-time confidence scoring.',
          kind: 'paragraph',
          confidence: 0.94,
        ),
        const BBoxItem(
          blockId: 'p0_b2',
          page: 0,
          block: 2,
          bbox: [0.10, 0.34, 0.50, 0.58],
          text: 'Key Performance Metrics:\n• 15ms Latency\n• 99.4% Accuracy\n• 300 DPI Native Raster',
          kind: 'list_item',
          confidence: 0.88,
        ),
        const BBoxItem(
          blockId: 'p0_b3',
          page: 0,
          block: 3,
          bbox: [0.52, 0.34, 0.90, 0.58],
          text: 'Quality Repair Loop Status:\nSelf-correction active.\nTarget threshold: 85%.',
          kind: 'paragraph',
          confidence: 0.54, // Degraded confidence to trigger repair loop!
        ),
        const BBoxItem(
          blockId: 'p0_b4',
          page: 0,
          block: 4,
          bbox: [0.10, 0.62, 0.90, 0.88],
          text: '| Parameter | Value | Status |\n| Concurrency | 4 | Optimal |\n| Pipeline | Hybrid | Active |',
          kind: 'table',
          confidence: 0.92,
        ),
      ],
    ];

    _simulationTimer = Timer.periodic(const Duration(milliseconds: 600), (timer) {
      step++;
      if (!_progressNotifier.state.isProcessing) {
        timer.cancel();
        return;
      }

      switch (step) {
        case 1:
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Rasterizing document pages at 300 DPI...',
            percent: 15.0,
            stage: 'Conversion',
          ));
          break;

        case 2:
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Detecting grounded layout structures...',
            percent: 30.0,
            stage: 'Detection',
          ));
          break;

        case 3:
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Running multimodal OCR recognition...',
            percent: 50.0,
            stage: 'OCR',
          ));
          // Stream initial blocks
          final boxes = sampleBoxesPerPage[0];
          for (int i = 0; i < 3; i++) {
            final b = boxes[i];
            _progressNotifier.handleWsFrame(WsBlockCompleteFrame(
              pageIdx: b.page,
              blockIdx: b.block,
              bbox: b.bbox,
              text: b.text,
              kind: b.kind ?? 'paragraph',
              confidence: b.confidence,
            ));
          }
          break;

        case 4:
          // Stream degraded box and remaining box
          final boxes = sampleBoxesPerPage[0];
          for (int i = 3; i < boxes.length; i++) {
            final b = boxes[i];
            _progressNotifier.handleWsFrame(WsBlockCompleteFrame(
              pageIdx: b.page,
              blockIdx: b.block,
              bbox: b.bbox,
              text: b.text,
              kind: b.kind ?? 'paragraph',
              confidence: b.confidence,
            ));
          }
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Evaluating block confidence thresholds...',
            percent: 65.0,
            stage: 'Refine / Quality Repair',
          ));
          break;

        case 5:
          // Trigger Quality Repair loop retry
          if (settings.qualityRepairEnabled) {
            _progressNotifier.handleWsFrame(const WsBlockRetryFrame(
              pageIdx: 0,
              blockIdx: 3,
              attempt: 1,
              confidence: 0.54,
              target: 0.85,
            ));
          }
          break;

        case 6:
          // Emit revised block
          if (settings.qualityRepairEnabled) {
            _progressNotifier.handleWsFrame(const WsBlockRevisedFrame(
              pageIdx: 0,
              blockIdx: 3,
              attempt: 1,
              bbox: [0.52, 0.34, 0.90, 0.58],
              text: 'Quality Repair Loop Status:\nSelf-correction active.\nTarget threshold: 85%.\n[Repaired: High Quality]',
              kind: 'paragraph',
              confidence: 0.96,
            ));
          }
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Enriching reading order & section hierarchy...',
            percent: 85.0,
            stage: 'Postprocess',
          ));
          break;

        case 7:
          _progressNotifier.handleWsFrame(const WsPageCompleteFrame(pageIdx: 0));
          _progressNotifier.handleWsFrame(const WsProgressFrame(
            status: 'Generating vector semantic embeddings...',
            percent: 95.0,
            stage: 'Embedding',
          ));
          break;

        case 8:
          timer.cancel();
          _progressNotifier.completeJob(message: 'Document OCR complete (5 blocks, 1 repaired)');
          break;
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return DocumentProvider(
      notifier: _documentNotifier,
      child: ProgressProvider(
        notifier: _progressNotifier,
        child: Builder(
          builder: (context) {
            final colors = context.docuVerse;
            final docState = DocumentProvider.of(context);
            final docNotifier = DocumentProvider.notifierOf(context);
            final progressState = ProgressProvider.of(context);

            final hasDoc = docState.hasDocument;
            final selectedBBox = docState.selectedBBox;

            return Scaffold(
              backgroundColor: colors.app,
              body: SafeArea(
                child: Column(
                  children: [
                    // Main Workstation Header Bar
                    _buildHeaderBar(context, colors, docState, docNotifier),

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
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              // Viewport + Side Inspector Split
                                              Expanded(
                                                child: Row(
                                                  crossAxisAlignment: CrossAxisAlignment.stretch,
                                                  children: [
                                                    // Main Viewport
                                                    Expanded(
                                                      child: DocumentViewport(
                                                        onBBoxSelected: (box) => docNotifier.selectBBox(box),
                                                      ),
                                                    ),

                                                    // Side BBox Inspector (if a box is selected)
                                                    if (selectedBBox != null) ...[
                                                      const SizedBox(width: 12),
                                                      SizedBox(
                                                        width: 320,
                                                        child: BBoxInspector(
                                                          bbox: selectedBBox,
                                                          onClose: () => docNotifier.selectBBox(null),
                                                        ),
                                                      ),
                                                    ],
                                                  ],
                                                ),
                                              ),

                                              // Multi-Page Strip (if doc has > 1 page)
                                              if (docState.pageCount > 1) ...[
                                                const SizedBox(height: 12),
                                                const PageStrip(orientation: Axis.horizontal),
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
                                            onSettingsChanged: (s) => setState(() => _processSettings = s),
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
                                              onBBoxSelected: (box) => docNotifier.selectBBox(box),
                                            ),
                                          ),
                                          if (selectedBBox != null) ...[
                                            const SizedBox(height: 12),
                                            BBoxInspector(
                                              bbox: selectedBBox,
                                              onClose: () => docNotifier.selectBBox(null),
                                            ),
                                          ],
                                          if (docState.pageCount > 1) ...[
                                            const SizedBox(height: 12),
                                            const PageStrip(orientation: Axis.horizontal),
                                          ],
                                          const SizedBox(height: 16),
                                          RightControlDock(
                                            settings: _processSettings,
                                            onSettingsChanged: (s) => setState(() => _processSettings = s),
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
                    if (hasDoc || progressState.isProcessing)
                      BottomProgressDock(
                        onCancelJob: () => _simulationTimer?.cancel(),
                      ),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  Widget _buildHeaderBar(
    BuildContext context,
    DocuVerseThemeTokens colors,
    DocumentViewModel docState,
    DocumentStateNotifier docNotifier,
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
          Row(
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
                  child: Icon(Icons.auto_stories_rounded, size: 18, color: Colors.white),
                ),
              ),
              const SizedBox(width: 12),
              Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'OmniScribe',
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
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontBody,
                      fontSize: 10,
                      color: colors.foregroundMuted,
                    ),
                  ),
                ],
              ),
            ],
          ),

          // Header Actions (Clear, Load New, Help)
          Row(
            children: [
              if (docState.hasDocument) ...[
                DocuVerseButton(
                  text: 'Clear Document',
                  variant: DocuVerseButtonVariant.ghost,
                  size: DocuVerseButtonSize.sm,
                  icon: const Icon(Icons.clear_all_rounded, size: 16),
                  onPressed: () {
                    _simulationTimer?.cancel();
                    docNotifier.clear();
                    _progressNotifier.reset();
                  },
                ),
                const SizedBox(width: 8),
              ],
              DocuVerseBadge(
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
