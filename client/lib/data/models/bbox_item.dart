/// Normalized bounding box element representing an OCR layout block.
class BBoxItem {
  const BBoxItem({
    required this.blockId,
    required this.page,
    required this.block,
    required this.bbox,
    required this.text,
    this.confidence,
    this.kind,
    this.revised,
    this.label,
  });

  /// Unique identifier for this block (e.g. 'p0_b1').
  final String blockId;

  /// 0-indexed or 1-indexed page index.
  final int page;

  /// Block index within the page.
  final int block;

  /// Normalized [x0, y0, x1, y1] in 0.0 .. 1.0 page coordinates.
  final List<double> bbox;

  /// Extracted text content for this block.
  final String text;

  /// Confidence score between 0.0 and 1.0 (if scored).
  final double? confidence;

  /// Block kind (e.g., 'paragraph', 'header', 'table', 'footer', 'caption').
  final String? kind;

  /// Whether this block was revised/repaired by the quality loop.
  final bool? revised;

  /// Human-readable label or classification tag.
  final String? label;

  double get x0 => bbox.isNotEmpty ? bbox[0] : 0.0;
  double get y0 => bbox.length > 1 ? bbox[1] : 0.0;
  double get x1 => bbox.length > 2 ? bbox[2] : 0.0;
  double get y1 => bbox.length > 3 ? bbox[3] : 0.0;
  double get width => (x1 - x0).abs();
  double get height => (y1 - y0).abs();

  BBoxItem copyWith({
    String? blockId,
    int? page,
    int? block,
    List<double>? bbox,
    String? text,
    double? confidence,
    String? kind,
    bool? revised,
    String? label,
  }) {
    return BBoxItem(
      blockId: blockId ?? this.blockId,
      page: page ?? this.page,
      block: block ?? this.block,
      bbox: bbox ?? this.bbox,
      text: text ?? this.text,
      confidence: confidence ?? this.confidence,
      kind: kind ?? this.kind,
      revised: revised ?? this.revised,
      label: label ?? this.label,
    );
  }

  factory BBoxItem.fromJson(Map<String, dynamic> json) {
    final rawBbox = json['bbox'];
    final coords = <double>[];
    if (rawBbox is List) {
      for (final item in rawBbox) {
        if (item is num) {
          coords.add(item.toDouble());
        }
      }
    }

    return BBoxItem(
      blockId: json['block_id']?.toString() ??
          'p${json['page'] ?? 0}_b${json['block'] ?? 0}',
      page: (json['page'] as num?)?.toInt() ?? 0,
      block: (json['block'] as num?)?.toInt() ?? 0,
      bbox: coords.length == 4 ? coords : const [0.0, 0.0, 1.0, 1.0],
      text: json['text']?.toString() ?? '',
      confidence: (json['confidence'] as num?)?.toDouble(),
      kind: json['kind']?.toString(),
      revised: json['revised'] as bool?,
      label: json['label']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    final map = <String, dynamic>{
      'block_id': blockId,
      'page': page,
      'block': block,
      'bbox': bbox,
      'text': text,
    };
    if (confidence != null) map['confidence'] = confidence;
    if (kind != null) map['kind'] = kind;
    if (revised != null) map['revised'] = revised;
    if (label != null) map['label'] = label;
    return map;
  }
}
