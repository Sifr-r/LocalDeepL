import 'dart:ui' show Offset;

import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/models/document_result.dart';

/// Immutable state model for the OmniScribe Workstation.
///
/// Encapsulates loaded document data, canvas viewport state (zoom, pan, bboxes),
/// and real-time OCR execution/progress metrics.
@immutable
class WorkstationState {
  WorkstationState({
    // Document data
    this.loadedBytes,
    this.filename,
    this.filePath,
    this.pageCount = 0,
    this.selectedPageIndex = 0,
    List<PageResult> pages = const <PageResult>[],
    // Canvas viewport
    this.selectedBBox,
    this.hoveredBBox,
    this.showBBoxes = true,
    this.showHeatmap = true,
    this.zoomScale = 1.0,
    this.panOffset = Offset.zero,
    this.filterKind,
    // OCR & Progress
    this.isProcessing = false,
    this.activeJobId,
    this.lastSubmittedJobId,
    this.channelId,
    this.percent = 0,
    this.stage = 'Idle',
    this.statusMessage = '',
    List<String> warnings = const <String>[],
    Map<String, int> blockRetryCounts = const <String, int>{},
    this.qualitySummary,
    this.avgConfidence,
    this.processedBlocks = 0,
    this.totalBlocks = 0,
    this.scoredBlocks = 0,
    this.trustSummary,
    this.error,
    this.textArtifactId,
    this.textArtifactToken,
    // Keyboard shortcut plumbing: bumped each time the AppShell fires
    // Ctrl+O (or any other trigger) so listeners (e.g. the upload dropzone)
    // can react by opening the native file picker. A monotonically
    // increasing int keeps the change observable by Riverpod listeners.
    this.filePickSignal = 0,
  })  : // Defensively copy mutable inputs so the @immutable contract holds even
        // when callers pass regular (growable) collections.
        // [loadedBytes] is a Uint8List (a typed buffer view); we do NOT copy it
        // here to avoid the cost of duplicating multi-MB PDF payloads on every
        // state transition. Callers MUST treat `state.loadedBytes` as read-only
        // — see [loadedBytes] for the full convention.
        pages = List<PageResult>.unmodifiable(pages),
        warnings = List<String>.unmodifiable(warnings),
        blockRetryCounts = Map<String, int>.unmodifiable(blockRetryCounts);

  // Document data
  final Uint8List? loadedBytes;
  final String? filename;
  final String? filePath;
  final int pageCount;
  final int selectedPageIndex;
  final List<PageResult> pages;

  // Canvas viewport
  final BBoxItem? selectedBBox;
  final BBoxItem? hoveredBBox;
  final bool showBBoxes;
  final bool showHeatmap;
  final double zoomScale;
  final Offset panOffset;
  final String? filterKind;

  // OCR & Progress
  final bool isProcessing;
  final String? activeJobId;
  final String? lastSubmittedJobId;
  final String? channelId;
  final int percent;
  final String stage;
  final String statusMessage;
  final List<String> warnings;
  final Map<String, int> blockRetryCounts;
  final QualitySummary? qualitySummary;
  final double? avgConfidence;
  final int processedBlocks;
  final int totalBlocks;
  final int scoredBlocks;
  final TrustSummary? trustSummary;
  final String? error;
  final String? textArtifactId;
  final String? textArtifactToken;

  /// Monotonically increasing counter incremented whenever the workstation
  /// should open its native file picker (Ctrl+O shortcut, "Open" toolbar
  /// action, etc.). Consumers compare the value across rebuilds to detect
  /// a pick-request and react exactly once per increment.
  final int filePickSignal;

  /// Ordered stages of the OCR pipeline.
  static const List<String> pipelineStages = [
    'Conversion',
    'Detection',
    'OCR',
    'Refine / Quality Repair',
    'Postprocess',
    'Embedding',
  ];

  /// Whether a document is currently loaded.
  ///
  /// A document is considered loaded when the workstation holds either the
  /// raw PDF bytes (`loadedBytes`) or an on-disk path (`filePath`). Populated
  /// `pages` alone are NOT sufficient — [processOcrSync] / [processOcrAsync]
  /// both reject documents with no source bytes, and consumers should treat
  /// "has pages" and "can run OCR" as the same precondition.
  bool get hasDocument => loadedBytes != null || filePath != null;

  /// Active [PageResult] based on [selectedPageIndex].
  PageResult? get currentPage {
    if (pages.isEmpty ||
        selectedPageIndex < 0 ||
        selectedPageIndex >= pages.length) {
      return null;
    }
    return pages[selectedPageIndex];
  }

  /// Bounding boxes on the active page, optionally filtered by [filterKind].
  List<BBoxItem> get currentPageBBoxes {
    final page = currentPage;
    if (page == null) return const <BBoxItem>[];
    if (filterKind == null || filterKind!.isEmpty || filterKind == 'all') {
      return page.bboxes;
    }
    return page.bboxes.where((b) => b.kind == filterKind).toList();
  }

  /// Flattened list of all bounding boxes across all loaded pages.
  List<BBoxItem> get allBBoxes =>
      pages.expand((p) => p.bboxes).toList();

  /// Total quality retry attempts across all blocks.
  int get totalRetriesAttempted =>
      blockRetryCounts.values.fold(0, (sum, count) => sum + count);

  /// Number of repaired blocks according to summary or bbox revision flags.
  int get repairedCount =>
      qualitySummary?.repairedCount ??
      allBBoxes.where((b) => b.revised ?? false).length;

  /// Formatted integer progress percentage.
  int get percentInt => percent;

  /// Numeric index of active pipeline stage.
  ///
  /// Returns the position of [stage] within [pipelineStages], or `-1` when the
  /// stage is not part of the pipeline (e.g. `'Idle'`, `'Complete'`, `'Error'`,
  /// `'Cancelled'`). Callers that render a stepper UI should treat `-1` as
  /// "no active step" and skip highlighting instead of defaulting to `0`.
  int get currentStageIndex => pipelineStages.indexOf(stage);

  /// Confidence statistics across all scored boxes in the document.
  ConfidenceSummary? get confidenceSummary {
    final scored = allBBoxes.where((b) => b.confidence != null).toList();
    if (scored.isEmpty) return null;

    var sum = 0.0;
    var min = 1.0;
    var max = 0.0;

    for (final box in scored) {
      final c = box.confidence!;
      sum += c;
      if (c < min) min = c;
      if (c > max) max = c;
    }

    return ConfidenceSummary(
      average: sum / scored.length,
      min: min,
      max: max,
      count: scored.length,
    );
  }

  WorkstationState copyWith({
    // Document data
    Uint8List? loadedBytes,
    bool clearLoadedBytes = false,
    String? filename,
    bool clearFilename = false,
    String? filePath,
    bool clearFilePath = false,
    int? pageCount,
    int? selectedPageIndex,
    List<PageResult>? pages,
    // Canvas viewport
    BBoxItem? selectedBBox,
    bool clearSelectedBBox = false,
    BBoxItem? hoveredBBox,
    bool clearHoveredBBox = false,
    bool? showBBoxes,
    bool? showHeatmap,
    double? zoomScale,
    Offset? panOffset,
    String? filterKind,
    bool clearFilterKind = false,
    // OCR & Progress
    bool? isProcessing,
    String? activeJobId,
    bool clearActiveJobId = false,
    String? lastSubmittedJobId,
    bool clearLastSubmittedJobId = false,
    String? channelId,
    bool clearChannelId = false,
    int? percent,
    String? stage,
    String? statusMessage,
    List<String>? warnings,
    Map<String, int>? blockRetryCounts,
    QualitySummary? qualitySummary,
    bool clearQualitySummary = false,
    double? avgConfidence,
    bool clearAvgConfidence = false,
    int? processedBlocks,
    int? totalBlocks,
    int? scoredBlocks,
    bool clearScoredBlocks = false,
    TrustSummary? trustSummary,
    bool clearTrustSummary = false,
    String? error,
    bool clearError = false,
    String? textArtifactId,
    bool clearTextArtifactId = false,
    String? textArtifactToken,
    bool clearTextArtifactToken = false,
    // Keyboard shortcut plumbing
    int? filePickSignal,
  }) {
    return WorkstationState(
      loadedBytes: clearLoadedBytes ? null : (loadedBytes ?? this.loadedBytes),
      filename: clearFilename ? null : (filename ?? this.filename),
      filePath: clearFilePath ? null : (filePath ?? this.filePath),
      pageCount: pageCount ?? this.pageCount,
      selectedPageIndex: selectedPageIndex ?? this.selectedPageIndex,
      pages: pages == null ? this.pages : List<PageResult>.unmodifiable(pages),
      selectedBBox:
          clearSelectedBBox ? null : (selectedBBox ?? this.selectedBBox),
      hoveredBBox: clearHoveredBBox ? null : (hoveredBBox ?? this.hoveredBBox),
      showBBoxes: showBBoxes ?? this.showBBoxes,
      showHeatmap: showHeatmap ?? this.showHeatmap,
      zoomScale: zoomScale ?? this.zoomScale,
      panOffset: panOffset ?? this.panOffset,
      filterKind: clearFilterKind ? null : (filterKind ?? this.filterKind),
      isProcessing: isProcessing ?? this.isProcessing,
      activeJobId: clearActiveJobId ? null : (activeJobId ?? this.activeJobId),
      lastSubmittedJobId: clearLastSubmittedJobId
          ? null
          : (lastSubmittedJobId ?? this.lastSubmittedJobId),
      channelId: clearChannelId ? null : (channelId ?? this.channelId),
      percent: percent ?? this.percent,
      stage: stage ?? this.stage,
      statusMessage: statusMessage ?? this.statusMessage,
      warnings:
          warnings == null ? this.warnings : List<String>.unmodifiable(warnings),
      blockRetryCounts: blockRetryCounts == null
          ? this.blockRetryCounts
          : Map<String, int>.unmodifiable(blockRetryCounts),
      qualitySummary:
          clearQualitySummary ? null : (qualitySummary ?? this.qualitySummary),
      avgConfidence:
          clearAvgConfidence ? null : (avgConfidence ?? this.avgConfidence),
      processedBlocks: processedBlocks ?? this.processedBlocks,
      totalBlocks: totalBlocks ?? this.totalBlocks,
      scoredBlocks:
          clearScoredBlocks ? 0 : (scoredBlocks ?? this.scoredBlocks),
      trustSummary:
          clearTrustSummary ? null : (trustSummary ?? this.trustSummary),
      error: clearError ? null : (error ?? this.error),
      textArtifactId:
          clearTextArtifactId ? null : (textArtifactId ?? this.textArtifactId),
      textArtifactToken: clearTextArtifactToken
          ? null
          : (textArtifactToken ?? this.textArtifactToken),
      filePickSignal: filePickSignal ?? this.filePickSignal,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is WorkstationState &&
          runtimeType == other.runtimeType &&
          listEquals(loadedBytes, other.loadedBytes) &&
          filename == other.filename &&
          filePath == other.filePath &&
          pageCount == other.pageCount &&
          selectedPageIndex == other.selectedPageIndex &&
          listEquals(pages, other.pages) &&
          selectedBBox == other.selectedBBox &&
          hoveredBBox == other.hoveredBBox &&
          showBBoxes == other.showBBoxes &&
          showHeatmap == other.showHeatmap &&
          zoomScale == other.zoomScale &&
          panOffset == other.panOffset &&
          filterKind == other.filterKind &&
          isProcessing == other.isProcessing &&
          activeJobId == other.activeJobId &&
          lastSubmittedJobId == other.lastSubmittedJobId &&
          channelId == other.channelId &&
          percent == other.percent &&
          stage == other.stage &&
          statusMessage == other.statusMessage &&
          listEquals(warnings, other.warnings) &&
          mapEquals(blockRetryCounts, other.blockRetryCounts) &&
          qualitySummary == other.qualitySummary &&
          avgConfidence == other.avgConfidence &&
          processedBlocks == other.processedBlocks &&
          totalBlocks == other.totalBlocks &&
          scoredBlocks == other.scoredBlocks &&
          trustSummary == other.trustSummary &&
          error == other.error &&
          textArtifactId == other.textArtifactId &&
          textArtifactToken == other.textArtifactToken &&
          filePickSignal == other.filePickSignal;

  @override
  int get hashCode => Object.hashAll([
        loadedBytes != null ? Object.hashAll(loadedBytes!) : null,
        filename,
        filePath,
        pageCount,
        selectedPageIndex,
        Object.hashAll(pages),
        selectedBBox,
        hoveredBBox,
        showBBoxes,
        showHeatmap,
        zoomScale,
        panOffset,
        filterKind,
        isProcessing,
        activeJobId,
        lastSubmittedJobId,
        channelId,
        percent,
        stage,
        statusMessage,
        Object.hashAll(warnings),
        // blockRetryCounts is compared order-insensitively via [mapEquals],
        // so its hash must also be order-insensitive. Plain
        // `Object.hashAllUnordered(entries)` does NOT work here because
        // `MapEntry.hashCode` is identity-based — different MapEntry
        // instances for the same key/value would hash differently. Instead,
        // fold a content-based per-entry hash (`Object.hash(key, value)`)
        // into an unordered accumulator.
        Object.hashAllUnordered(
          blockRetryCounts.entries.map((e) => Object.hash(e.key, e.value)),
        ),
        qualitySummary,
        avgConfidence,
        processedBlocks,
        totalBlocks,
        scoredBlocks,
        trustSummary,
        error,
        textArtifactId,
        textArtifactToken,
        filePickSignal,
      ]);
}
