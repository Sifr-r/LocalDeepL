import 'package:flutter/foundation.dart';

/// Quality Repair Loop summary metrics from WebSocket frame.
@immutable
class QualitySummary {
  const QualitySummary({
    required this.scope,
    required this.target,
    required this.avgConfidence,
    required this.repairedCount,
    required this.belowTargetCount,
    this.pageIdx,
  });

  final String scope;
  final double target;
  final double avgConfidence;
  final int repairedCount;
  final int belowTargetCount;
  final int? pageIdx;

  int get avgConfidencePercent => (avgConfidence * 100).round();
  int get targetPercent => (target * 100).round();

  factory QualitySummary.fromJson(Map<String, dynamic> json) {
    return QualitySummary(
      scope: json['scope'] as String? ?? 'document',
      target: (json['target'] as num?)?.toDouble() ?? 0.85,
      avgConfidence: (json['avg_confidence'] as num?)?.toDouble() ?? 0.0,
      repairedCount: (json['repaired_count'] as num?)?.toInt() ?? 0,
      belowTargetCount: (json['below_target_count'] as num?)?.toInt() ?? 0,
      pageIdx: (json['page_idx'] as num?)?.toInt(),
    );
  }

  Map<String, dynamic> toJson() => {
        'scope': scope,
        'target': target,
        'avg_confidence': avgConfidence,
        'repaired_count': repairedCount,
        'below_target_count': belowTargetCount,
        if (pageIdx != null) 'page_idx': pageIdx,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is QualitySummary &&
          runtimeType == other.runtimeType &&
          scope == other.scope &&
          target == other.target &&
          avgConfidence == other.avgConfidence &&
          repairedCount == other.repairedCount &&
          belowTargetCount == other.belowTargetCount &&
          pageIdx == other.pageIdx;

  @override
  int get hashCode => Object.hash(
        scope,
        target,
        avgConfidence,
        repairedCount,
        belowTargetCount,
        pageIdx,
      );
}
