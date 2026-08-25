import 'package:flutter/foundation.dart';
import 'bbox_item.dart';
import 'quality_summary.dart';

/// Processing progress state for live WebSocket streaming updates.
@immutable
class JobProgressState {
  const JobProgressState({
    this.isProcessing = false,
    this.activeJobId,
    this.channelId,
    this.percent = 0.0,
    this.stage = 'Idle',
    this.statusMessage = 'Ready',
    this.warnings = const [],
    this.blockRetryCounts = const {},
    this.repairedBlocks = const [],
    this.qualitySummary,
    this.completedPages = const {},
    this.failedPages = const {},
    this.totalBlocks = 0,
    this.processedBlocks = 0,
    this.avgConfidence,
  });

  final bool isProcessing;
  final String? activeJobId;
  final String? channelId;
  final double percent;
  final String stage;
  final String statusMessage;
  final List<String> warnings;
  final Map<String, int> blockRetryCounts;
  final List<BBoxItem> repairedBlocks;
  final QualitySummary? qualitySummary;
  final Set<int> completedPages;
  final Set<int> failedPages;
  final int totalBlocks;
  final int processedBlocks;
  final double? avgConfidence;

  int get percentInt => percent.clamp(0.0, 100.0).round();

  int get totalRetriesAttempted {
    return blockRetryCounts.values.fold(0, (sum, count) => sum + count);
  }

  int get repairedCount => repairedBlocks.length;

  /// Ordered stages for the live workstation stage stepper
  static const List<String> pipelineStages = [
    'Conversion',
    'Detection',
    'OCR',
    'Refine / Quality Repair',
    'Postprocess',
    'Embedding',
  ];

  int get currentStageIndex {
    final lower = stage.toLowerCase();
    if (lower.contains('convert') || lower.contains('raster')) return 0;
    if (lower.contains('detect') || lower.contains('layout') || lower.contains('ground')) return 1;
    if (lower.contains('ocr') || lower.contains('recogni') || lower.contains('transcrib')) return 2;
    if (lower.contains('refine') || lower.contains('repair') || lower.contains('correct') || lower.contains('retry')) return 3;
    if (lower.contains('postprocess') || lower.contains('enrich') || lower.contains('align') || lower.contains('table') || lower.contains('order')) return 4;
    if (lower.contains('embed') || lower.contains('index') || lower.contains('vector')) return 5;
    if (lower.contains('complete') || lower.contains('finish')) return 6;
    return -1;
  }

  JobProgressState copyWith({
    bool? isProcessing,
    String? activeJobId,
    bool clearActiveJobId = false,
    String? channelId,
    bool clearChannelId = false,
    double? percent,
    String? stage,
    String? statusMessage,
    List<String>? warnings,
    Map<String, int>? blockRetryCounts,
    List<BBoxItem>? repairedBlocks,
    QualitySummary? qualitySummary,
    bool clearQualitySummary = false,
    Set<int>? completedPages,
    Set<int>? failedPages,
    int? totalBlocks,
    int? processedBlocks,
    double? avgConfidence,
  }) {
    return JobProgressState(
      isProcessing: isProcessing ?? this.isProcessing,
      activeJobId: clearActiveJobId ? null : (activeJobId ?? this.activeJobId),
      channelId: clearChannelId ? null : (channelId ?? this.channelId),
      percent: percent ?? this.percent,
      stage: stage ?? this.stage,
      statusMessage: statusMessage ?? this.statusMessage,
      warnings: warnings ?? this.warnings,
      blockRetryCounts: blockRetryCounts ?? this.blockRetryCounts,
      repairedBlocks: repairedBlocks ?? this.repairedBlocks,
      qualitySummary: clearQualitySummary ? null : (qualitySummary ?? this.qualitySummary),
      completedPages: completedPages ?? this.completedPages,
      failedPages: failedPages ?? this.failedPages,
      totalBlocks: totalBlocks ?? this.totalBlocks,
      processedBlocks: processedBlocks ?? this.processedBlocks,
      avgConfidence: avgConfidence ?? this.avgConfidence,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is JobProgressState &&
          runtimeType == other.runtimeType &&
          isProcessing == other.isProcessing &&
          activeJobId == other.activeJobId &&
          channelId == other.channelId &&
          percent == other.percent &&
          stage == other.stage &&
          statusMessage == other.statusMessage &&
          listEquals(warnings, other.warnings) &&
          mapEquals(blockRetryCounts, other.blockRetryCounts) &&
          listEquals(repairedBlocks, other.repairedBlocks) &&
          qualitySummary == other.qualitySummary &&
          setEquals(completedPages, other.completedPages) &&
          setEquals(failedPages, other.failedPages) &&
          totalBlocks == other.totalBlocks &&
          processedBlocks == other.processedBlocks &&
          avgConfidence == other.avgConfidence;

  @override
  int get hashCode => Object.hash(
        isProcessing,
        activeJobId,
        channelId,
        percent,
        stage,
        statusMessage,
        Object.hashAll(warnings),
        Object.hashAll(blockRetryCounts.entries),
        Object.hashAll(repairedBlocks),
        qualitySummary,
        Object.hashAll(completedPages),
        Object.hashAll(failedPages),
        totalBlocks,
        processedBlocks,
        avgConfidence,
      );
}
