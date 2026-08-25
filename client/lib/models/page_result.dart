import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'bbox_item.dart';

/// Represents a single page's OCR result with bounding boxes and optional raster preview.
@immutable
class PageResult {
  const PageResult({
    required this.page,
    this.width,
    this.height,
    this.bboxes = const [],
    this.text,
    this.imageUrl,
    this.previewBytes,
  });

  final int page;
  final double? width;
  final double? height;
  final List<BBoxItem> bboxes;
  final String? text;
  final String? imageUrl;
  final Uint8List? previewBytes;

  double get aspectRatio {
    if (width != null && height != null && height! > 0) {
      return width! / height!;
    }
    // Default portrait letter/A4 aspect ratio
    return 8.5 / 11.0;
  }

  factory PageResult.fromJson(Map<String, dynamic> json) {
    final rawBoxes = json['bboxes'] as List<dynamic>? ?? [];
    final bboxesList = rawBoxes
        .whereType<Map<String, dynamic>>()
        .map((b) => BBoxItem.fromJson(b))
        .toList();

    return PageResult(
      page: (json['page'] as num?)?.toInt() ?? 0,
      width: (json['width'] as num?)?.toDouble(),
      height: (json['height'] as num?)?.toDouble(),
      bboxes: bboxesList,
      text: json['text'] as String?,
      imageUrl: json['image_url'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'page': page,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        'bboxes': bboxes.map((b) => b.toJson()).toList(),
        if (text != null) 'text': text,
        if (imageUrl != null) 'image_url': imageUrl,
      };

  PageResult copyWith({
    int? page,
    double? width,
    double? height,
    List<BBoxItem>? bboxes,
    String? text,
    String? imageUrl,
    Uint8List? previewBytes,
  }) {
    return PageResult(
      page: page ?? this.page,
      width: width ?? this.width,
      height: height ?? this.height,
      bboxes: bboxes ?? this.bboxes,
      text: text ?? this.text,
      imageUrl: imageUrl ?? this.imageUrl,
      previewBytes: previewBytes ?? this.previewBytes,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is PageResult &&
          runtimeType == other.runtimeType &&
          page == other.page &&
          width == other.width &&
          height == other.height &&
          listEquals(bboxes, other.bboxes) &&
          text == other.text &&
          imageUrl == other.imageUrl;

  @override
  int get hashCode => Object.hash(
        page,
        width,
        height,
        Object.hashAll(bboxes),
        text,
        imageUrl,
      );
}
