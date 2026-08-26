import 'dart:convert';
import 'dart:typed_data';

import 'bbox_item.dart';

/// Trust and quality analysis metrics extracted from X-Document-Trust header.
class TrustSummary {
  const TrustSummary({
    required this.blockCount,
    required this.scoredCount,
    required this.flaggedCount,
    required this.average,
    this.histogram = const {},
    this.flagCounts = const {},
  });

  final int blockCount;
  final int scoredCount;
  final int flaggedCount;
  final double average;
  final Map<String, int> histogram;
  final Map<String, int> flagCounts;

  factory TrustSummary.fromJson(Map<String, dynamic> json) {
    final hist = <String, int>{};
    if (json['histogram'] is Map) {
      (json['histogram'] as Map).forEach((k, v) {
        if (v is num) hist[k.toString()] = v.toInt();
      });
    }

    final flags = <String, int>{};
    if (json['flag_counts'] is Map) {
      (json['flag_counts'] as Map).forEach((k, v) {
        if (v is num) flags[k.toString()] = v.toInt();
      });
    }

    return TrustSummary(
      blockCount: (json['block_count'] as num?)?.toInt() ?? 0,
      scoredCount: (json['scored_count'] as num?)?.toInt() ?? 0,
      flaggedCount: (json['flagged_count'] as num?)?.toInt() ?? 0,
      average: (json['average'] as num?)?.toDouble() ?? 0.0,
      histogram: hist,
      flagCounts: flags,
    );
  }

  static TrustSummary? tryParseHeader(String? rawHeader) {
    if (rawHeader == null || rawHeader.isEmpty) return null;
    try {
      final decoded = jsonDecode(rawHeader);
      if (decoded is Map<String, dynamic>) {
        return TrustSummary.fromJson(decoded);
      }
    } catch (_) {}
    return null;
  }

  Map<String, dynamic> toJson() => {
        'block_count': blockCount,
        'scored_count': scoredCount,
        'flagged_count': flaggedCount,
        'average': average,
        'histogram': histogram,
        'flag_counts': flagCounts,
      };
}

/// Structured page analysis representation.
class PageResult {
  const PageResult({
    required this.page,
    this.width,
    this.height,
    this.bboxes = const [],
    this.text,
    this.raw,
  });

  final int page;
  final double? width;
  final double? height;
  final List<BBoxItem> bboxes;
  final String? text;
  final Map<String, dynamic>? raw;

  factory PageResult.fromJson(Map<String, dynamic> json) {
    final boxList = <BBoxItem>[];
    if (json['bboxes'] is List) {
      for (final item in json['bboxes'] as List) {
        if (item is Map<String, dynamic>) {
          boxList.add(BBoxItem.fromJson(item));
        }
      }
    }

    return PageResult(
      page: (json['page'] as num?)?.toInt() ?? 0,
      width: (json['width'] as num?)?.toDouble(),
      height: (json['height'] as num?)?.toDouble(),
      bboxes: boxList,
      text: json['text']?.toString(),
      raw: json,
    );
  }

  Map<String, dynamic> toJson() => {
        'page': page,
        if (width != null) 'width': width,
        if (height != null) 'height': height,
        'bboxes': bboxes.map((b) => b.toJson()).toList(),
        if (text != null) 'text': text,
      };
}

/// Confidence distribution statistics.
class ConfidenceSummary {
  const ConfidenceSummary({
    required this.average,
    required this.min,
    required this.max,
  });

  final double average;
  final double min;
  final double max;

  factory ConfidenceSummary.fromJson(Map<String, dynamic> json) {
    return ConfidenceSummary(
      average: (json['average'] as num?)?.toDouble() ?? 0.0,
      min: (json['min'] as num?)?.toDouble() ?? 0.0,
      max: (json['max'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() => {
        'average': average,
        'min': min,
        'max': max,
      };
}

/// Reference to a stored text artifact in OmniScribe artifact store.
class TextArtifactHandle {
  const TextArtifactHandle({
    required this.id,
    required this.token,
    this.pageCount,
  });

  final String id;
  final String token;
  final int? pageCount;

  factory TextArtifactHandle.fromJson(Map<String, dynamic> json) {
    return TextArtifactHandle(
      id: json['id']?.toString() ?? '',
      token: json['token']?.toString() ?? '',
      pageCount: (json['pageCount'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'token': token,
        if (pageCount != null) 'pageCount': pageCount,
      };
}

/// High-level presentation ViewModel for workstation document view.
class DocumentViewModel {
  const DocumentViewModel({
    this.pages = const [],
    this.textArtifacts = const [],
    this.textArtifact,
    this.textArtifactId,
    this.textArtifactToken,
    this.filename,
    this.selectedPageIndex = 0,
    this.bboxes = const [],
    this.confidence,
    this.confidenceSummary,
    this.pageCount = 0,
    this.trustSummary,
  });

  final List<PageResult> pages;
  final List<TextArtifactHandle> textArtifacts;
  final TextArtifactHandle? textArtifact;
  final String? textArtifactId;
  final String? textArtifactToken;
  final String? filename;
  final int selectedPageIndex;
  final List<BBoxItem> bboxes;
  final double? confidence;
  final ConfidenceSummary? confidenceSummary;
  final int pageCount;
  final TrustSummary? trustSummary;

  DocumentViewModel copyWith({
    List<PageResult>? pages,
    List<TextArtifactHandle>? textArtifacts,
    TextArtifactHandle? textArtifact,
    String? textArtifactId,
    String? textArtifactToken,
    String? filename,
    int? selectedPageIndex,
    List<BBoxItem>? bboxes,
    double? confidence,
    ConfidenceSummary? confidenceSummary,
    int? pageCount,
    TrustSummary? trustSummary,
  }) {
    return DocumentViewModel(
      pages: pages ?? this.pages,
      textArtifacts: textArtifacts ?? this.textArtifacts,
      textArtifact: textArtifact ?? this.textArtifact,
      textArtifactId: textArtifactId ?? this.textArtifactId,
      textArtifactToken: textArtifactToken ?? this.textArtifactToken,
      filename: filename ?? this.filename,
      selectedPageIndex: selectedPageIndex ?? this.selectedPageIndex,
      bboxes: bboxes ?? this.bboxes,
      confidence: confidence ?? this.confidence,
      confidenceSummary: confidenceSummary ?? this.confidenceSummary,
      pageCount: pageCount ?? this.pageCount,
      trustSummary: trustSummary ?? this.trustSummary,
    );
  }

  factory DocumentViewModel.fromJson(Map<String, dynamic> json) {
    final pagesList = <PageResult>[];
    if (json['pages'] is List) {
      for (final p in json['pages'] as List) {
        if (p is Map<String, dynamic>) pagesList.add(PageResult.fromJson(p));
      }
    }

    final artsList = <TextArtifactHandle>[];
    if (json['textArtifacts'] is List) {
      for (final a in json['textArtifacts'] as List) {
        if (a is Map<String, dynamic>) {
          artsList.add(TextArtifactHandle.fromJson(a));
        }
      }
    }

    final boxList = <BBoxItem>[];
    if (json['bboxes'] is List) {
      for (final b in json['bboxes'] as List) {
        if (b is Map<String, dynamic>) boxList.add(BBoxItem.fromJson(b));
      }
    }

    return DocumentViewModel(
      pages: pagesList,
      textArtifacts: artsList,
      textArtifact: json['textArtifact'] is Map<String, dynamic>
          ? TextArtifactHandle.fromJson(
              json['textArtifact'] as Map<String, dynamic>)
          : null,
      textArtifactId: json['textArtifactId']?.toString(),
      textArtifactToken: json['textArtifactToken']?.toString(),
      filename: json['filename']?.toString(),
      selectedPageIndex: (json['selectedPageIndex'] as num?)?.toInt() ?? 0,
      bboxes: boxList,
      confidence: (json['confidence'] as num?)?.toDouble(),
      confidenceSummary: json['confidenceSummary'] is Map<String, dynamic>
          ? ConfidenceSummary.fromJson(
              json['confidenceSummary'] as Map<String, dynamic>)
          : null,
      pageCount: (json['pageCount'] as num?)?.toInt() ?? pagesList.length,
      trustSummary: json['trustSummary'] is Map<String, dynamic>
          ? TrustSummary.fromJson(json['trustSummary'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() => {
        'pages': pages.map((p) => p.toJson()).toList(),
        'textArtifacts': textArtifacts.map((a) => a.toJson()).toList(),
        if (textArtifact != null) 'textArtifact': textArtifact!.toJson(),
        if (textArtifactId != null) 'textArtifactId': textArtifactId,
        if (textArtifactToken != null) 'textArtifactToken': textArtifactToken,
        if (filename != null) 'filename': filename,
        'selectedPageIndex': selectedPageIndex,
        'bboxes': bboxes.map((b) => b.toJson()).toList(),
        if (confidence != null) 'confidence': confidence,
        if (confidenceSummary != null)
          'confidenceSummary': confidenceSummary!.toJson(),
        'pageCount': pageCount,
        if (trustSummary != null) 'trustSummary': trustSummary!.toJson(),
      };
}

/// Result of synchronous OCR containing output PDF bytes and metadata headers.
class ProcessOcrResult {
  const ProcessOcrResult({
    required this.pdfBytes,
    required this.headers,
    this.trustSummary,
    this.textArtifactId,
    this.textArtifactToken,
  });

  final Uint8List pdfBytes;
  final Map<String, String> headers;
  final TrustSummary? trustSummary;
  final String? textArtifactId;
  final String? textArtifactToken;
}
