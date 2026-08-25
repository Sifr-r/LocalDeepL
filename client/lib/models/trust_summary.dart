import 'package:flutter/foundation.dart';

/// Trust score and statistical metrics for OCR output verification.
@immutable
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

  int get averagePercent => (average * 100).round();

  factory TrustSummary.fromJson(Map<String, dynamic> json) {
    final rawHist = json['histogram'] as Map<String, dynamic>? ?? {};
    final hist = rawHist.map((k, v) => MapEntry(k, (v as num).toInt()));

    final rawFlags = json['flag_counts'] as Map<String, dynamic>? ?? {};
    final flags = rawFlags.map((k, v) => MapEntry(k, (v as num).toInt()));

    return TrustSummary(
      blockCount: (json['block_count'] as num?)?.toInt() ?? 0,
      scoredCount: (json['scored_count'] as num?)?.toInt() ?? 0,
      flaggedCount: (json['flagged_count'] as num?)?.toInt() ?? 0,
      average: (json['average'] as num?)?.toDouble() ?? 0.0,
      histogram: hist,
      flagCounts: flags,
    );
  }

  Map<String, dynamic> toJson() => {
        'block_count': blockCount,
        'scored_count': scoredCount,
        'flagged_count': flaggedCount,
        'average': average,
        'histogram': histogram,
        'flag_counts': flagCounts,
      };

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is TrustSummary &&
          runtimeType == other.runtimeType &&
          blockCount == other.blockCount &&
          scoredCount == other.scoredCount &&
          flaggedCount == other.flaggedCount &&
          average == other.average &&
          mapEquals(histogram, other.histogram) &&
          mapEquals(flagCounts, other.flagCounts);

  @override
  int get hashCode => Object.hash(
        blockCount,
        scoredCount,
        flaggedCount,
        average,
        Object.hashAll(histogram.entries),
        Object.hashAll(flagCounts.entries),
      );
}
