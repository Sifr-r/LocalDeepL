import 'dart:math' as math;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/models/document_view_model.dart';
import 'package:omniscribe_client/models/page_result.dart';
import 'package:omniscribe_client/state/document_provider.dart';
import 'package:omniscribe_client/state/document_state.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'bbox_painter.dart';

/// GPU-Accelerated Document Viewport with InteractiveViewer zoom/pan,
/// custom BBoxPainter overlay, hit-testing, and layer controls.
class DocumentViewport extends StatefulWidget {
  const DocumentViewport({
    super.key,
    this.onBBoxSelected,
  });

  final ValueChanged<BBoxItem?>? onBBoxSelected;

  @override
  State<DocumentViewport> createState() => _DocumentViewportState();
}

class _DocumentViewportState extends State<DocumentViewport> {
  final TransformationController _transformController =
      TransformationController();
  final GlobalKey _canvasKey = GlobalKey();

  double _currentScale = 1.0;

  @override
  void initState() {
    super.initState();
    _transformController.addListener(_onTransformChanged);
  }

  @override
  void dispose() {
    _transformController.removeListener(_onTransformChanged);
    _transformController.dispose();
    super.dispose();
  }

  void _onTransformChanged() {
    final scale = _transformController.value.getMaxScaleOnAxis();
    if ((scale - _currentScale).abs() > 0.01) {
      setState(() {
        _currentScale = scale;
      });
    }
  }

  void _zoomIn() {
    final Matrix4 matrix = _transformController.value.clone();
    matrix.scale(1.25, 1.25);
    _transformController.value = matrix;
  }

  void _zoomOut() {
    final Matrix4 matrix = _transformController.value.clone();
    matrix.scale(0.8, 0.8);
    _transformController.value = matrix;
  }

  void _resetZoom() {
    _transformController.value = Matrix4.identity();
  }

  void _handleTapUp(TapUpDetails details, Size canvasSize,
      List<BBoxItem> bboxes, DocumentStateNotifier docNotifier) {
    if (canvasSize.width <= 0 || canvasSize.height <= 0 || bboxes.isEmpty) {
      docNotifier.selectBBox(null);
      widget.onBBoxSelected?.call(null);
      return;
    }

    final localPos = details.localPosition;
    final normX = (localPos.dx / canvasSize.width).clamp(0.0, 1.0);
    final normY = (localPos.dy / canvasSize.height).clamp(0.0, 1.0);

    // Find all bboxes containing this point
    final hits = bboxes.where((b) {
      return normX >= b.x0 && normX <= b.x1 && normY >= b.y0 && normY <= b.y1;
    }).toList();

    if (hits.isEmpty) {
      docNotifier.selectBBox(null);
      widget.onBBoxSelected?.call(null);
    } else {
      // Pick the most specific (smallest area) box
      hits.sort((a, b) => (a.width * a.height).compareTo(b.width * b.height));
      final selected = hits.first;
      docNotifier.selectBBox(selected);
      widget.onBBoxSelected?.call(selected);
    }
  }

  void _handlePointerHover(PointerHoverEvent event, Size canvasSize,
      List<BBoxItem> bboxes, DocumentStateNotifier docNotifier) {
    if (canvasSize.width <= 0 || canvasSize.height <= 0 || bboxes.isEmpty) {
      docNotifier.hoverBBox(null);
      return;
    }

    final localPos = event.localPosition;
    final normX = (localPos.dx / canvasSize.width).clamp(0.0, 1.0);
    final normY = (localPos.dy / canvasSize.height).clamp(0.0, 1.0);

    final hits = bboxes.where((b) {
      return normX >= b.x0 && normX <= b.x1 && normY >= b.y0 && normY <= b.y1;
    }).toList();

    if (hits.isEmpty) {
      docNotifier.hoverBBox(null);
    } else {
      hits.sort((a, b) => (a.width * a.height).compareTo(b.width * b.height));
      docNotifier.hoverBBox(hits.first);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final docState = DocumentProvider.of(context);
    final docNotifier = DocumentProvider.notifierOf(context);

    final PageResult? currentPage = docState.currentPage;
    final bboxes = docState.currentPageBBoxes;
    final totalPages = docState.pageCount;
    final currentPageIndex = docState.selectedPageIndex;

    return Container(
      decoration: BoxDecoration(
        color: colors.app,
        border: Border.all(color: colors.border),
        borderRadius: BorderRadius.all(Radius.circular(colors.cardRadius)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 1. Viewport Top Ribbon / Toolbar
          _buildTopRibbon(context, docState, docNotifier, colors),

          // 2. Interactive Zoomable / Pannable Document Viewport
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.only(
                bottomLeft: Radius.circular(colors.cardRadius as double),
                bottomRight: Radius.circular(colors.cardRadius as double),
              ),
              child: Stack(
                children: [
                  // Subtle Spatial Grid Background
                  Positioned.fill(
                    child: CustomPaint(
                      painter: _GridBackgroundPainter(
                        gridColor: colors.border.withValues(alpha: 0.35),
                      ),
                    ),
                  ),

                  // Interactive Viewer Canvas
                  Positioned.fill(
                    child: InteractiveViewer(
                      transformationController: _transformController,
                      minScale: 0.2,
                      maxScale: 6.0,
                      boundaryMargin: const EdgeInsets.all(300),
                      child: Center(
                        child: _buildDocumentCanvas(
                          context,
                          docState,
                          docNotifier,
                          currentPage,
                          bboxes,
                          colors,
                        ),
                      ),
                    ),
                  ),

                  // Floating Quick-Action Layer / Zoom Controls (Bottom Right)
                  Positioned(
                    right: 16,
                    bottom: 16,
                    child:
                        _buildFloatingControls(colors, docState, docNotifier),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTopRibbon(
    BuildContext context,
    DocumentViewModel docState,
    DocumentStateNotifier docNotifier,
    DocuVerseThemeTokens colors,
  ) {
    final hasDoc = docState.hasDocument;
    final currentPageIndex = docState.selectedPageIndex;
    final totalPages = math.max(1, docState.pageCount);

    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: colors.cardRaised,
        border: Border(bottom: BorderSide(color: colors.border)),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(colors.cardRadius),
          topRight: Radius.circular(colors.cardRadius),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // Left: Document Title & Badge
          Expanded(
            child: Row(
              children: [
                Icon(
                  Icons.article_outlined,
                  size: 18,
                  color: colors.brand,
                ),
                const SizedBox(width: 8),
                Text(
                  'GPU Document Viewport',
                  style: TextStyle(
                    fontFamily: DocuVerseTypography.fontDisplay,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: colors.foreground,
                  ),
                ),
                if (docState.filename != null) ...[
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      '• ${docState.filename!}',
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontMono,
                        fontSize: 12,
                        color: colors.foregroundMuted,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
                if (docState.allBBoxes.isNotEmpty) ...[
                  const SizedBox(width: 10),
                  DocuVerseBadge(
                    text: '${docState.allBBoxes.length} BBOXES',
                    variant: DocuVerseBadgeVariant.brand,
                    size: DocuVerseBadgeSize.sm,
                  ),
                ],
              ],
            ),
          ),

          // Right: Page Navigator & Layer Switches
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Page Navigation
              if (hasDoc && totalPages > 1) ...[
                IconButton(
                  icon: const Icon(Icons.chevron_left_rounded, size: 20),
                  tooltip: 'Previous page',
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  color: currentPageIndex > 0
                      ? colors.foreground
                      : colors.foregroundSubtle,
                  onPressed: currentPageIndex > 0
                      ? () => docNotifier.selectPage(currentPageIndex - 1)
                      : null,
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Text(
                    'Page ${currentPageIndex + 1} of $totalPages',
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontMono,
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                      color: colors.foreground,
                    ),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right_rounded, size: 20),
                  tooltip: 'Next page',
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  color: currentPageIndex < totalPages - 1
                      ? colors.foreground
                      : colors.foregroundSubtle,
                  onPressed: currentPageIndex < totalPages - 1
                      ? () => docNotifier.selectPage(currentPageIndex + 1)
                      : null,
                ),
                const SizedBox(width: 12),
                Container(width: 1, height: 20, color: colors.border),
                const SizedBox(width: 12),
              ],

              // Layer Toggles
              Tooltip(
                message: docState.showBBoxes
                    ? 'Hide bounding boxes'
                    : 'Show bounding boxes',
                child: InkWell(
                  onTap: () => docNotifier.toggleBBoxes(),
                  borderRadius: BorderRadius.circular(4),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: docState.showBBoxes
                          ? colors.brand.withValues(alpha: 0.15)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                        color: docState.showBBoxes
                            ? colors.brand.withValues(alpha: 0.4)
                            : colors.border,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.crop_free_rounded,
                          size: 14,
                          color: docState.showBBoxes
                              ? colors.brand
                              : colors.foregroundMuted,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Boxes',
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontBody,
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: docState.showBBoxes
                                ? colors.brand
                                : colors.foregroundMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Tooltip(
                message: docState.showHeatmap
                    ? 'Disable confidence heatmap'
                    : 'Enable confidence heatmap',
                child: InkWell(
                  onTap: () => docNotifier.toggleHeatmap(),
                  borderRadius: BorderRadius.circular(4),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: docState.showHeatmap
                          ? colors.success.withValues(alpha: 0.15)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                        color: docState.showHeatmap
                            ? colors.success.withValues(alpha: 0.4)
                            : colors.border,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.gradient_rounded,
                          size: 14,
                          color: docState.showHeatmap
                              ? colors.success
                              : colors.foregroundMuted,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Heatmap',
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontBody,
                            fontSize: 11,
                            fontWeight: FontWeight.w500,
                            color: docState.showHeatmap
                                ? colors.success
                                : colors.foregroundMuted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildDocumentCanvas(
    BuildContext context,
    DocumentViewModel docState,
    DocumentStateNotifier docNotifier,
    PageResult? currentPage,
    List<BBoxItem> bboxes,
    DocuVerseThemeTokens colors,
  ) {
    // Determine canvas physical aspect ratio & base size
    const double baseWidth = 680.0;
    final double aspectRatio = currentPage?.aspectRatio ?? (8.5 / 11.0);
    final double baseHeight = baseWidth / aspectRatio;
    final canvasSize = Size(baseWidth, baseHeight);

    return Container(
      key: _canvasKey,
      width: baseWidth,
      height: baseHeight,
      decoration: BoxDecoration(
        color: colors.card,
        borderRadius: BorderRadius.circular(6),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.4),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
        border: Border.all(color: colors.borderStrong, width: 1.0),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(6),
        child: MouseRegion(
          onHover: (e) =>
              _handlePointerHover(e, canvasSize, bboxes, docNotifier),
          onExit: (_) => docNotifier.hoverBBox(null),
          child: GestureDetector(
            onTapUp: (details) =>
                _handleTapUp(details, canvasSize, bboxes, docNotifier),
            child: Stack(
              fit: StackFit.expand,
              children: [
                // 1. Page Background Raster / Placeholder
                if (currentPage?.previewBytes != null)
                  Image.memory(
                    currentPage!.previewBytes!,
                    fit: BoxFit.fill,
                  )
                else
                  _buildPagePlaceholder(colors, docState),

                // 2. Custom Painted Bounding Box Overlays
                CustomPaint(
                  size: canvasSize,
                  painter: BBoxPainter(
                    bboxes: bboxes,
                    selectedBBox: docState.selectedBBox,
                    hoveredBBox: docState.hoveredBBox,
                    colors: colors,
                    showBBoxes: docState.showBBoxes,
                    showHeatmap: docState.showHeatmap,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPagePlaceholder(
      DocuVerseThemeTokens colors, DocumentViewModel docState) {
    return Container(
      color: colors.card,
      padding: const EdgeInsets.all(32),
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.description_outlined,
              size: 48,
              color: colors.foregroundSubtle.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 12),
            Text(
              docState.hasDocument
                  ? 'Page ${docState.selectedPageIndex + 1}'
                  : 'No Document Loaded',
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontDisplay,
                fontSize: 16,
                fontWeight: FontWeight.w600,
                color: colors.foregroundMuted,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              docState.hasDocument
                  ? 'Normalized bbox overlay rendered in GPU viewport'
                  : 'Drop or select a PDF / image file from the dropzone to start',
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontBody,
                fontSize: 12,
                color: colors.foregroundSubtle,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFloatingControls(
    DocuVerseThemeTokens colors,
    DocumentViewModel docState,
    DocumentStateNotifier docNotifier,
  ) {
    final zoomPercent = (_currentScale * 100).round();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: colors.cardRaised.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(colors.cardRadius),
        border: Border.all(color: colors.borderStrong),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.25),
            blurRadius: 12,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            icon: const Icon(Icons.remove, size: 16),
            tooltip: 'Zoom out',
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            padding: EdgeInsets.zero,
            color: colors.foreground,
            onPressed: _zoomOut,
          ),
          InkWell(
            onTap: _resetZoom,
            borderRadius: BorderRadius.circular(4),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              child: Text(
                '$zoomPercent%',
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontMono,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: colors.brand,
                ),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add, size: 16),
            tooltip: 'Zoom in',
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            padding: EdgeInsets.zero,
            color: colors.foreground,
            onPressed: _zoomIn,
          ),
          Container(
              width: 1,
              height: 16,
              color: colors.border,
              margin: const EdgeInsets.symmetric(horizontal: 4)),
          IconButton(
            icon: const Icon(Icons.fit_screen_outlined, size: 16),
            tooltip: 'Reset Zoom (100%)',
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            padding: EdgeInsets.zero,
            color: colors.foregroundMuted,
            onPressed: _resetZoom,
          ),
        ],
      ),
    );
  }
}

class _GridBackgroundPainter extends CustomPainter {
  const _GridBackgroundPainter({required this.gridColor});
  final Color gridColor;

  @override
  void paint(Canvas canvas, Size size) {
    const double step = 24.0;
    final paint = Paint()
      ..color = gridColor
      ..strokeWidth = 0.5;

    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _GridBackgroundPainter oldDelegate) {
    return oldDelegate.gridColor != gridColor;
  }
}
