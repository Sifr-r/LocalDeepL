import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'bbox_item.dart';
import 'page_result.dart';
import 'trust_summary.dart';

/// Summary of confidence across scored boxes.
@immutable
class ConfidenceSummary {
  const ConfidenceSummary({
    required this.average,
    required this.min,
    required this.max,
    required this.count,
  });

  final double average;
  final double min;
  final double max;
  final int count;

  int get averagePercent => (average * 100).round();
  int get minPercent => (min * 100).round();
  int get maxPercent => (max * 100).round();
}

/// View model representing the document workstation state.
@immutable
class DocumentViewModel {
  const DocumentViewModel({
    this.loadedBytes,
    this.filePath,
    this.filename,
    this.pageCount = 0,
    this.selectedPageIndex = 0,
    this.pages = const [],
    this.selectedBBox,
    this.hoveredBBox,
    this.showBBoxes = true,
    this.showHeatmap = true,
    this.filterKind,
    this.trustSummary,
    this.zoomScale = 1.0,
    this.panOffset = Offset.zero,
  });

  final Uint8List? loadedBytes;
  final String? filePath;
  final String? filename;
  final int pageCount;
  final int selectedPageIndex;
  final List<PageResult> pages;
  final BBoxItem? selectedBBox;
  final BBoxItem? hoveredBBox;
  final bool showBBoxes;
  final bool showHeatmap;
  final String? filterKind;
  final TrustSummary? trustSummary;
  final double zoomScale;
  final Offset panOffset;

  bool get hasDocument => loadedBytes != null || filePath != null || pages.isNotEmpty;

  PageResult? get currentPage {
    if (pages.isEmpty || selectedPageIndex < 0 || selectedPageIndex >= pages.length) {
      return null;
    }
    return pages[selectedPageIndex];
  }

  List<BBoxItem> get currentPageBBoxes {
    final page = currentPage;
    if (page == null) return const [];
    if (filterKind == null || filterKind!.isEmpty || filterKind == 'all') {
      return page.bboxes;
    }
    return page.bboxes.where((b) => b.kind == filterKind).toList();
  }

  List<BBoxItem> get allBBoxes {
    return pages.expand((p) => p.bboxes).toList();
  }

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

  DocumentViewModel copyWith({
    Uint8List? loadedBytes,
    String? filePath,
    String? filename,
    int? pageCount,
    int? selectedPageIndex,
    List<PageResult>? pages,
    BBoxItem? selectedBBox,
    bool clearSelectedBBox = false,
    BBoxItem? hoveredBBox,
    bool clearHoveredBBox = false,
    bool? showBBoxes,
    bool? showHeatmap,
    String? filterKind,
    bool clearFilterKind = false,
    TrustSummary? trustSummary,
    double? zoomScale,
    Offset? panOffset,
  }) {
    return DocumentViewModel(
      loadedBytes: loadedBytes ?? this.loadedBytes,
      filePath: filePath ?? this.filePath,
      filename: filename ?? this.filename,
      pageCount: pageCount ?? this.pageCount,
      selectedPageIndex: selectedPageIndex ?? this.selectedPageIndex,
      pages: pages ?? this.pages,
      selectedBBox: clearSelectedBBox ? null : (selectedBBox ?? this.selectedBBox),
      hoveredBBox: clearHoveredBBox ? null : (hoveredBBox ?? this.hoveredBBox),
      showBBoxes: showBBoxes ?? this.showBBoxes,
      showHeatmap: showHeatmap ?? this.showHeatmap,
      filterKind: clearFilterKind ? null : (filterKind ?? this.filterKind),
      trustSummary: trustSummary ?? this.trustSummary,
      zoomScale: zoomScale ?? this.zoomScale,
      panOffset: panOffset ?? this.panOffset,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is DocumentViewModel &&
          runtimeType == other.runtimeType &&
          filePath == other.filePath &&
          filename == other.filename &&
          pageCount == other.pageCount &&
          selectedPageIndex == other.selectedPageIndex &&
          listEquals(pages, other.pages) &&
          selectedBBox == other.selectedBBox &&
          hoveredBBox == other.hoveredBBox &&
          showBBoxes == other.showBBoxes &&
          showHeatmap == other.showHeatmap &&
          filterKind == other.filterKind &&
          trustSummary == other.trustSummary &&
          zoomScale == other.zoomScale &&
          panOffset == other.panOffset;

  @override
  int get hashCode => Object.hash(
        filePath,
        filename,
        pageCount,
        selectedPageIndex,
        Object.hashAll(pages),
        selectedBBox,
        hoveredBBox,
        showBBoxes,
        showHeatmap,
        filterKind,
        trustSummary,
        zoomScale,
        panOffset,
      );
}
