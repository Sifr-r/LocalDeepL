import 'package:flutter/foundation.dart';

/// Normalized Bounding Box Item matching BBoxItem in api.ts & backend schemas.
/// Coordinates are normalized [x0, y0, x1, y1] where 0 <= x, y <= 1.
@immutable
class BBoxItem {
  const BBoxItem({
    required this.blockId,
    required this.page,
    required this.block,
    required this.bbox,
    required this.text,
    this.confidence,
    this.kind = 'paragraph',
    this.revised = false,
    this.label,
  });

  // Shape validation is performed in [fromJson] (the only construction entry
  // point for non-test data) so this constructor can stay `const`. Test data
  // that needs an invalid bbox should construct it directly through a
  // non-const helper, not through the public API.

  final String blockId;
  final int page;
  final int block;
  final List<double> bbox;
  final double? confidence;
  final String text;
  final String? kind;
  final bool revised;
  final String? label;

  double get x0 => bbox.isNotEmpty ? bbox[0].clamp(0.0, 1.0) : 0.0;
  double get y0 => bbox.length > 1 ? bbox[1].clamp(0.0, 1.0) : 0.0;
  double get x1 => bbox.length > 2 ? bbox[2].clamp(0.0, 1.0) : 1.0;
  double get y1 => bbox.length > 3 ? bbox[3].clamp(0.0, 1.0) : 1.0;

  double get width => (x1 - x0).clamp(0.0, 1.0);
  double get height => (y1 - y0).clamp(0.0, 1.0);

  int? get confidencePercent => confidence != null ? (confidence! * 100).round() : null;

  /// Confidence classification for color-coding:
  /// - High: >= 0.85 (Green)
  /// - Medium: 0.60..0.84 (Yellow / Amber)
  /// - Low: < 0.60 (Red / Coral)
  String get confidenceTier {
    if (confidence == null) return 'unknown';
    if (confidence! >= 0.85) return 'high';
    if (confidence! >= 0.60) return 'medium';
    return 'low';
  }

  factory BBoxItem.fromJson(Map<String, dynamic> json) {
    final rawBbox = json['bbox'] as List<dynamic>? ?? [0.0, 0.0, 1.0, 1.0];
    final bboxList = rawBbox.map((e) => (e as num).toDouble()).toList();
    assert(
      bboxList.length == 4,
      'BBox coordinates must have exactly 4 numbers [x0, y0, x1, y1]',
    );
    final pageIdx = (json['page'] as num?)?.toInt() ?? (json['page_idx'] as num?)?.toInt() ?? 0;
    final blockIdx = (json['block'] as num?)?.toInt() ?? (json['block_idx'] as num?)?.toInt() ?? 0;
    final blockId = json['block_id'] as String? ?? 'p${pageIdx}_b$blockIdx';

    return BBoxItem(
      blockId: blockId,
      page: pageIdx,
      block: blockIdx,
      bbox: bboxList,
      text: json['text'] as String? ?? '',
      confidence: (json['confidence'] as num?)?.toDouble(),
      kind: json['kind'] as String? ?? 'paragraph',
      revised: json['revised'] as bool? ?? false,
      label: json['label'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'block_id': blockId,
        'page': page,
        'block': block,
        'bbox': bbox,
        'confidence': confidence,
        'text': text,
        'kind': kind,
        'revised': revised,
        if (label != null) 'label': label,
      };

  BBoxItem copyWith({
    String? blockId,
    int? page,
    int? block,
    List<double>? bbox,
    double? confidence,
    String? text,
    String? kind,
    bool? revised,
    String? label,
  }) {
    return BBoxItem(
      blockId: blockId ?? this.blockId,
      page: page ?? this.page,
      block: block ?? this.block,
      bbox: bbox ?? this.bbox,
      confidence: confidence ?? this.confidence,
      text: text ?? this.text,
      kind: kind ?? this.kind,
      revised: revised ?? this.revised,
      label: label ?? this.label,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is BBoxItem &&
          runtimeType == other.runtimeType &&
          blockId == other.blockId &&
          page == other.page &&
          block == other.block &&
          listEquals(bbox, other.bbox) &&
          confidence == other.confidence &&
          text == other.text &&
          kind == other.kind &&
          revised == other.revised &&
          label == other.label;

  @override
  int get hashCode => Object.hash(
        blockId,
        page,
        block,
        Object.hashAll(bbox),
        confidence,
        text,
        kind,
        revised,
        label,
      );
}
