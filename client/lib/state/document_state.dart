import 'dart:typed_data';
import 'dart:ui' show Offset;
import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/models/document_view_model.dart';
import 'package:omniscribe_client/models/page_result.dart';
import 'package:omniscribe_client/models/trust_summary.dart';

/// State notifier managing document view model, active page, bboxes, and selection.
class DocumentStateNotifier extends ChangeNotifier {
  DocumentStateNotifier([DocumentViewModel? initialState])
      : _state = initialState ?? const DocumentViewModel();

  DocumentViewModel _state;
  DocumentViewModel get state => _state;

  /// Loads a document from raw bytes and/or file path.
  void loadDocument(
    Uint8List? bytes,
    String? filename, {
    int pageCount = 1,
    String? filePath,
  }) {
    final pages = List<PageResult>.generate(
      pageCount > 0 ? pageCount : 1,
      (index) => PageResult(page: index),
    );

    _state = DocumentViewModel(
      loadedBytes: bytes,
      filePath: filePath,
      filename: filename,
      pageCount: pages.length,
      selectedPageIndex: 0,
      pages: pages,
      selectedBBox: null,
      hoveredBBox: null,
      showBBoxes: true,
      showHeatmap: true,
      zoomScale: 1.0,
      panOffset: Offset.zero,
    );
    notifyListeners();
  }

  /// Sets the currently active page index (0-indexed)
  void selectPage(int pageIndex) {
    if (pageIndex < 0 || (_state.pageCount > 0 && pageIndex >= _state.pageCount)) {
      return;
    }
    _state = _state.copyWith(
      selectedPageIndex: pageIndex,
      clearSelectedBBox: true,
      clearHoveredBBox: true,
    );
    notifyListeners();
  }

  /// Replaces all bounding boxes for a specific page.
  void setBBoxes(int page, List<BBoxItem> bboxes) {
    final updatedPages = List<PageResult>.from(_state.pages);

    // Ensure pages list is long enough
    while (updatedPages.length <= page) {
      updatedPages.add(PageResult(page: updatedPages.length));
    }

    updatedPages[page] = updatedPages[page].copyWith(bboxes: bboxes);

    _state = _state.copyWith(
      pages: updatedPages,
      pageCount: updatedPages.length,
    );
    notifyListeners();
  }

  /// Adds a new bounding box or updates an existing bounding box on a page.
  void addOrUpdateBBox(int page, BBoxItem bbox) {
    final updatedPages = List<PageResult>.from(_state.pages);

    while (updatedPages.length <= page) {
      updatedPages.add(PageResult(page: updatedPages.length));
    }

    final currentPage = updatedPages[page];
    final currentBBoxes = List<BBoxItem>.from(currentPage.bboxes);
    final existingIdx = currentBBoxes.indexWhere(
      (b) => b.blockId == bbox.blockId || (b.block == bbox.block && b.page == bbox.page),
    );

    if (existingIdx >= 0) {
      currentBBoxes[existingIdx] = bbox;
    } else {
      currentBBoxes.add(bbox);
    }

    updatedPages[page] = currentPage.copyWith(bboxes: currentBBoxes);

    // If this bbox is currently selected, update selectedBBox too
    BBoxItem? newSelected = _state.selectedBBox;
    if (_state.selectedBBox != null &&
        (_state.selectedBBox!.blockId == bbox.blockId ||
            (_state.selectedBBox!.page == bbox.page && _state.selectedBBox!.block == bbox.block))) {
      newSelected = bbox;
    }

    _state = _state.copyWith(
      pages: updatedPages,
      pageCount: updatedPages.length,
      selectedBBox: newSelected,
    );
    notifyListeners();
  }

  /// Selects or deselects a bounding box.
  void selectBBox(BBoxItem? bbox) {
    if (_state.selectedBBox == bbox) return;
    _state = _state.copyWith(
      selectedBBox: bbox,
      clearSelectedBBox: bbox == null,
    );
    notifyListeners();
  }

  /// Sets or clears the hovered bounding box for hover effects.
  void hoverBBox(BBoxItem? bbox) {
    if (_state.hoveredBBox == bbox) return;
    _state = _state.copyWith(
      hoveredBBox: bbox,
      clearHoveredBBox: bbox == null,
    );
    notifyListeners();
  }

  /// Updates zoom scale and pan offset for the canvas viewport.
  void setZoomPan({double? zoom, Offset? pan}) {
    _state = _state.copyWith(
      zoomScale: zoom != null ? zoom.clamp(0.2, 5.0) : _state.zoomScale,
      panOffset: pan ?? _state.panOffset,
    );
    notifyListeners();
  }

  /// Resets zoom and pan to defaults (1.0, Offset.zero).
  void resetZoomPan() {
    _state = _state.copyWith(
      zoomScale: 1.0,
      panOffset: Offset.zero,
    );
    notifyListeners();
  }

  /// Toggles visibility of bounding boxes.
  void toggleBBoxes([bool? show]) {
    _state = _state.copyWith(
      showBBoxes: show ?? !_state.showBBoxes,
    );
    notifyListeners();
  }

  /// Toggles confidence heatmap coloring.
  void toggleHeatmap([bool? show]) {
    _state = _state.copyWith(
      showHeatmap: show ?? !_state.showHeatmap,
    );
    notifyListeners();
  }

  /// Filters bounding boxes by block kind (paragraph, heading, table, etc.)
  void setFilterKind(String? kind) {
    _state = _state.copyWith(
      filterKind: kind,
      clearFilterKind: kind == null || kind.isEmpty || kind == 'all',
    );
    notifyListeners();
  }

  /// Updates trust metrics summary.
  void setTrustSummary(TrustSummary? summary) {
    _state = _state.copyWith(trustSummary: summary);
    notifyListeners();
  }

  /// Sets raster preview bytes for a page.
  void setPagePreview(int page, Uint8List previewBytes) {
    final updatedPages = List<PageResult>.from(_state.pages);
    if (page >= 0 && page < updatedPages.length) {
      updatedPages[page] = updatedPages[page].copyWith(previewBytes: previewBytes);
      _state = _state.copyWith(pages: updatedPages);
      notifyListeners();
    }
  }

  /// Clears the loaded document and resets state.
  void clear() {
    _state = const DocumentViewModel();
    notifyListeners();
  }
}
