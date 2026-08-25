import 'package:flutter/foundation.dart';
import 'bbox_item.dart';
import 'quality_summary.dart';

/// Sealed base class for WebSocket envelopes emitted by OmniScribe backend.
@immutable
sealed class WsEnvelope {
  const WsEnvelope();

  factory WsEnvelope.fromJson(Map<String, dynamic> json) {
    final type = json['type'] as String?;

    if (type == null) {
      // Legacy ProgressFrame has no type discriminator
      if (json.containsKey('percent') || json.containsKey('stage') || json.containsKey('status')) {
        return WsProgressFrame(
          status: json['status'] as String? ?? '',
          percent: (json['percent'] as num?)?.toDouble() ?? 0.0,
          stage: json['stage'] as String? ?? '',
          warning: json['warning'] as bool? ?? false,
        );
      }
      return WsUnknownFrame(type: 'none', raw: json);
    }

    switch (type) {
      case 'block_complete':
        final rawBbox = (json['bbox'] as List<dynamic>?)?.map((e) => (e as num).toDouble()).toList() ?? [0.0, 0.0, 1.0, 1.0];
        final pageIdx = (json['page_idx'] as num?)?.toInt() ?? 0;
        final blockIdx = (json['block_idx'] as num?)?.toInt() ?? 0;
        return WsBlockCompleteFrame(
          pageIdx: pageIdx,
          blockIdx: blockIdx,
          bbox: rawBbox,
          text: json['text'] as String? ?? '',
          kind: json['kind'] as String? ?? 'paragraph',
          confidence: (json['confidence'] as num?)?.toDouble(),
        );

      case 'block_retry':
        return WsBlockRetryFrame(
          pageIdx: (json['page_idx'] as num?)?.toInt() ?? 0,
          blockIdx: (json['block_idx'] as num?)?.toInt() ?? 0,
          attempt: (json['attempt'] as num?)?.toInt() ?? 1,
          confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
          target: (json['target'] as num?)?.toDouble() ?? 0.85,
        );

      case 'block_revised':
        final rawBbox = (json['bbox'] as List<dynamic>?)?.map((e) => (e as num).toDouble()).toList() ?? [0.0, 0.0, 1.0, 1.0];
        return WsBlockRevisedFrame(
          pageIdx: (json['page_idx'] as num?)?.toInt() ?? 0,
          blockIdx: (json['block_idx'] as num?)?.toInt() ?? 0,
          attempt: (json['attempt'] as num?)?.toInt() ?? 1,
          bbox: rawBbox,
          text: json['text'] as String? ?? '',
          kind: json['kind'] as String? ?? 'paragraph',
          confidence: (json['confidence'] as num?)?.toDouble(),
        );

      case 'page_complete':
        return WsPageCompleteFrame(
          pageIdx: (json['page_idx'] as num?)?.toInt() ?? 0,
        );

      case 'quality_summary':
        return WsQualitySummaryFrame(
          summary: QualitySummary.fromJson(json),
        );

      case 'cancelled':
        return WsCancelledFrame(
          status: json['status'] as String? ?? 'Cancelled',
          percent: (json['percent'] as num?)?.toDouble() ?? 0.0,
          stage: json['stage'] as String? ?? 'Cancelled',
        );

      default:
        return WsUnknownFrame(type: type, raw: json);
    }
  }
}

class WsProgressFrame extends WsEnvelope {
  const WsProgressFrame({
    required this.status,
    required this.percent,
    required this.stage,
    this.warning = false,
  });

  final String status;
  final double percent;
  final String stage;
  final bool warning;
}

class WsBlockCompleteFrame extends WsEnvelope {
  const WsBlockCompleteFrame({
    required this.pageIdx,
    required this.blockIdx,
    required this.bbox,
    required this.text,
    required this.kind,
    this.confidence,
  });

  final int pageIdx;
  final int blockIdx;
  final List<double> bbox;
  final String text;
  final String kind;
  final double? confidence;

  BBoxItem toBBoxItem() => BBoxItem(
        blockId: 'p${pageIdx}_b$blockIdx',
        page: pageIdx,
        block: blockIdx,
        bbox: bbox,
        text: text,
        confidence: confidence,
        kind: kind,
        revised: false,
      );
}

class WsBlockRetryFrame extends WsEnvelope {
  const WsBlockRetryFrame({
    required this.pageIdx,
    required this.blockIdx,
    required this.attempt,
    required this.confidence,
    required this.target,
  });

  final int pageIdx;
  final int blockIdx;
  final int attempt;
  final double confidence;
  final double target;

  String get blockKey => 'p${pageIdx}_b$blockIdx';
}

class WsBlockRevisedFrame extends WsEnvelope {
  const WsBlockRevisedFrame({
    required this.pageIdx,
    required this.blockIdx,
    required this.attempt,
    required this.bbox,
    required this.text,
    required this.kind,
    this.confidence,
  });

  final int pageIdx;
  final int blockIdx;
  final int attempt;
  final List<double> bbox;
  final String text;
  final String kind;
  final double? confidence;

  BBoxItem toBBoxItem() => BBoxItem(
        blockId: 'p${pageIdx}_b$blockIdx',
        page: pageIdx,
        block: blockIdx,
        bbox: bbox,
        text: text,
        confidence: confidence,
        kind: kind,
        revised: true,
      );
}

class WsPageCompleteFrame extends WsEnvelope {
  const WsPageCompleteFrame({
    required this.pageIdx,
  });

  final int pageIdx;
}

class WsQualitySummaryFrame extends WsEnvelope {
  const WsQualitySummaryFrame({
    required this.summary,
  });

  final QualitySummary summary;
}

class WsCancelledFrame extends WsEnvelope {
  const WsCancelledFrame({
    required this.status,
    required this.percent,
    required this.stage,
  });

  final String status;
  final double percent;
  final String stage;
}

class WsUnknownFrame extends WsEnvelope {
  const WsUnknownFrame({
    required this.type,
    required this.raw,
  });

  final String type;
  final Map<String, dynamic> raw;
}
