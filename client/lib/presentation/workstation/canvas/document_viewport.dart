import 'dart:math' as math;
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/models/document_result.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/data/providers/workstation_state.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'bbox_painter.dart';

/// GPU-Accelerated Document Viewport with InteractiveViewer zoom/pan,
/// custom BBoxPainter overlay, hit-testing, and layer controls.
class DocumentViewport extends ConsumerStatefulWidget {
  const DocumentViewport({
    super.key,
    this.onBBoxSelected,
  });

  final ValueChanged<BBoxItem?>? onBBoxSelected;

  @override
  ConsumerState<DocumentViewport> createState() => _DocumentViewportState();
}

class _DocumentViewportState extends ConsumerState<DocumentViewport> {
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
    matrix.scaleByDouble(1.25, 1.25, 1.0, 1.0);
    _transformController.value = matrix;
  }

  void _zoomOut() {
    final Matrix4 matrix = _transformController.value.clone();
    matrix.scaleByDouble(0.8, 0.8, 1.0, 1.0);
    _transformController.value = matrix;
  }

  void _resetZoom() {
    _transformController.value = Matrix4.identity();
  }

  void _handleTapUp(TapUpDetails details, Size canvasSize,
      List<BBoxItem> bboxes, WorkstationNotifier notifier) {
    if (canvasSize.width <= 0 || canvasSize.height <= 0 || bboxes.isEmpty) {
      notifier.selectBBox(null);
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
      notifier.selectBBox(null);
      widget.onBBoxSelected?.call(null);
    } else {
      // Pick the most specific (smallest area) box
      hits.sort((a, b) => (a.width * a.height).compareTo(b.width * b.height));
      final selected = hits.first;
      notifier.selectBBox(selected);
      widget.onBBoxSelected?.call(selected);
    }
  }

  void _handlePointerHover(PointerHoverEvent event, Size canvasSize,
      List<BBoxItem> bboxes, WorkstationNotifier notifier) {
    if (canvasSize.width <= 0 || canvasSize.height <= 0 || bboxes.isEmpty) {
      notifier.hoverBBox(null);
      return;
    }

    final localPos = event.localPosition;
    final normX = (localPos.dx / canvasSize.width).clamp(0.0, 1.0);
    final normY = (localPos.dy / canvasSize.height).clamp(0.0, 1.0);

    final hits = bboxes.where((b) {
      return normX >= b.x0 && normX <= b.x1 && normY >= b.y0 && normY <= b.y1;
    }).toList();

    if (hits.isEmpty) {
      notifier.hoverBBox(null);
    } else {
      hits.sort((a, b) => (a.width * a.height).compareTo(b.width * b.height));
      notifier.hoverBBox(hits.first);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final wsState = ref.watch(workstationProvider);
    final notifier = ref.read(workstationProvider.notifier);

    final PageResult? currentPage = wsState.currentPage;
    final bboxes = wsState.currentPageBBoxes;

    return Container(
      decoration: BoxDecoration(
        color: colors.background,
        border: Border.all(color: colors.border),
        borderRadius: const BorderRadius.all(Radius.circular(8)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // 1. Viewport Top Ribbon / Toolbar
          _buildTopRibbon(context, wsState, notifier, colors),

          // 2. Interactive Zoomable / Pannable Document Viewport
          Expanded(
            child: ClipRRect(
              borderRadius: const BorderRadius.only(
                bottomLeft: Radius.circular(8),
                bottomRight: Radius.circular(8),
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
                          wsState,
                          notifier,
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
                    child: _buildFloatingControls(colors, wsState, notifier),
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
    WorkstationState wsState,
    WorkstationNotifier notifier,
    AppColorScheme colors,
  ) {
    final hasDoc = wsState.hasDocument;
    final currentPageIndex = wsState.selectedPageIndex;
    final totalPages = math.max(1, wsState.pageCount);

    return Container(
      height: 48,
      padding: const EdgeInsets.symmetric(horizontal: 16),
      decoration: BoxDecoration(
        color: colors.cardRaised,
        border: Border(bottom: BorderSide(color: colors.border)),
        borderRadius: const BorderRadius.only(
          topLeft: Radius.circular(8),
          topRight: Radius.circular(8),
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
                Flexible(
                  child: Text(
                    'GPU Document Viewport',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.titleSmall(
                      color: colors.textPrimary,
                    ),
                  ),
                ),
                if (wsState.filename != null) ...[
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      '• ${wsState.filename!}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: AppTypography.codeSmall(
                        color: colors.textMuted,
                      ),
                    ),
                  ),
                ],
                if (wsState.allBBoxes.isNotEmpty) ...[
                  const SizedBox(width: 10),
                  AppBadge(
                    label: '${wsState.allBBoxes.length} BBOXES',
                    variant: AppBadgeVariant.brand,
                    size: AppBadgeSize.sm,
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
                      ? colors.textPrimary
                      : colors.textMuted,
                  onPressed: currentPageIndex > 0
                      ? () => notifier.selectPage(currentPageIndex - 1)
                      : null,
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Text(
                    'Page ${currentPageIndex + 1} of $totalPages',
                    style: AppTypography.codeSmall(
                      color: colors.textPrimary,
                    ).copyWith(fontWeight: FontWeight.w500),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.chevron_right_rounded, size: 20),
                  tooltip: 'Next page',
                  padding: EdgeInsets.zero,
                  constraints:
                      const BoxConstraints(minWidth: 32, minHeight: 32),
                  color: currentPageIndex < totalPages - 1
                      ? colors.textPrimary
                      : colors.textMuted,
                  onPressed: currentPageIndex < totalPages - 1
                      ? () => notifier.selectPage(currentPageIndex + 1)
                      : null,
                ),
                const SizedBox(width: 12),
                Container(width: 1, height: 20, color: colors.border),
                const SizedBox(width: 12),
              ],

              // Layer Toggles
              Tooltip(
                message: wsState.showBBoxes
                    ? 'Hide bounding boxes'
                    : 'Show bounding boxes',
                child: InkWell(
                  onTap: () => notifier.toggleBBoxes(),
                  borderRadius: BorderRadius.circular(4),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: wsState.showBBoxes
                          ? colors.brand.withValues(alpha: 0.15)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                        color: wsState.showBBoxes
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
                          color: wsState.showBBoxes
                              ? colors.brand
                              : colors.textMuted,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Boxes',
                          style: AppTypography.bodySmall(
                            color: wsState.showBBoxes
                                ? colors.brand
                                : colors.textMuted,
                          ).copyWith(fontSize: 11, fontWeight: FontWeight.w500),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Tooltip(
                message: wsState.showHeatmap
                    ? 'Disable confidence heatmap'
                    : 'Enable confidence heatmap',
                child: InkWell(
                  onTap: () => notifier.toggleHeatmap(),
                  borderRadius: BorderRadius.circular(4),
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: wsState.showHeatmap
                          ? colors.success.withValues(alpha: 0.15)
                          : Colors.transparent,
                      borderRadius: BorderRadius.circular(4),
                      border: Border.all(
                        color: wsState.showHeatmap
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
                          color: wsState.showHeatmap
                              ? colors.success
                              : colors.textMuted,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          'Heatmap',
                          style: AppTypography.bodySmall(
                            color: wsState.showHeatmap
                                ? colors.success
                                : colors.textMuted,
                          ).copyWith(fontSize: 11, fontWeight: FontWeight.w500),
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
    WorkstationState wsState,
    WorkstationNotifier notifier,
    PageResult? currentPage,
    List<BBoxItem> bboxes,
    AppColorScheme colors,
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
              _handlePointerHover(e, canvasSize, bboxes, notifier),
          onExit: (_) => notifier.hoverBBox(null),
          child: GestureDetector(
            onTapUp: (details) =>
                _handleTapUp(details, canvasSize, bboxes, notifier),
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
                  _buildPagePlaceholder(colors, wsState),

                // 2. Custom Painted Bounding Box Overlays
                CustomPaint(
                  size: canvasSize,
                  painter: BBoxPainter(
                    bboxes: bboxes,
                    selectedBBox: wsState.selectedBBox,
                    hoveredBBox: wsState.hoveredBBox,
                    colors: colors,
                    showBBoxes: wsState.showBBoxes,
                    showHeatmap: wsState.showHeatmap,
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
      AppColorScheme colors, WorkstationState wsState) {
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
              color: colors.textMuted.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 12),
            Text(
              wsState.hasDocument
                  ? 'Page ${wsState.selectedPageIndex + 1}'
                  : 'No Document Loaded',
              style: AppTypography.titleMedium(
                color: colors.textMuted,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              wsState.hasDocument
                  ? 'Normalized bbox overlay rendered in GPU viewport'
                  : 'Drop or select a PDF / image file from the dropzone to start',
              style: AppTypography.bodySmall(
                color: colors.textMuted,
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFloatingControls(
    AppColorScheme colors,
    WorkstationState wsState,
    WorkstationNotifier notifier,
  ) {
    final zoomPercent = (_currentScale * 100).round();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: colors.cardRaised.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(8),
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
            color: colors.textPrimary,
            onPressed: _zoomOut,
          ),
          InkWell(
            onTap: _resetZoom,
            borderRadius: BorderRadius.circular(4),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              child: Text(
                '$zoomPercent%',
                style: AppTypography.codeSmall(
                  color: colors.brand,
                ).copyWith(fontWeight: FontWeight.w600),
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.add, size: 16),
            tooltip: 'Zoom in',
            constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
            padding: EdgeInsets.zero,
            color: colors.textPrimary,
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
            color: colors.textMuted,
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
