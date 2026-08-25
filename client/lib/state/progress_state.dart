import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/models/job_progress_state.dart';
import 'package:omniscribe_client/models/quality_summary.dart';
import 'package:omniscribe_client/models/ws_envelope.dart';

/// Callback type for forwarding streamed bounding box updates to DocumentStateNotifier
typedef OnBBoxStreamedCallback = void Function(int page, BBoxItem bbox);

/// State notifier managing OCR job progress, live WebSocket streaming events, quality repair metrics.
class ProgressStateNotifier extends ChangeNotifier {
  ProgressStateNotifier([JobProgressState? initialState])
      : _state = initialState ?? const JobProgressState();

  JobProgressState _state;
  JobProgressState get state => _state;

  OnBBoxStreamedCallback? onBBoxStreamed;

  /// Starts tracking a new OCR job.
  void startJob(String jobId, String? channelId) {
    _state = JobProgressState(
      isProcessing: true,
      activeJobId: jobId,
      channelId: channelId,
      percent: 0.0,
      stage: 'Conversion',
      statusMessage: 'Starting OCR pipeline...',
      warnings: const [],
      blockRetryCounts: const {},
      repairedBlocks: const [],
      qualitySummary: null,
      completedPages: const {},
      failedPages: const {},
      totalBlocks: 0,
      processedBlocks: 0,
      avgConfidence: null,
    );
    notifyListeners();
  }

  /// Processes a parsed WebSocket frame envelope.
  void handleWsFrame(WsEnvelope frame) {
    switch (frame) {
      case WsProgressFrame p:
        final updatedWarnings = p.warning && p.status.isNotEmpty
            ? [..._state.warnings, p.status]
            : _state.warnings;

        _state = _state.copyWith(
          percent: p.percent.clamp(0.0, 100.0),
          stage: p.stage.isNotEmpty ? p.stage : _state.stage,
          statusMessage: p.status.isNotEmpty ? p.status : _state.statusMessage,
          warnings: updatedWarnings,
        );
        notifyListeners();

      case WsBlockCompleteFrame b:
        final item = b.toBBoxItem();
        final newProcessed = _state.processedBlocks + 1;
        final newTotal = _state.totalBlocks < newProcessed ? newProcessed : _state.totalBlocks;

        double? updatedAvg = _state.avgConfidence;
        if (b.confidence != null) {
          if (updatedAvg == null) {
            updatedAvg = b.confidence;
          } else {
            updatedAvg = (updatedAvg * (_state.processedBlocks) + b.confidence!) / newProcessed;
          }
        }

        _state = _state.copyWith(
          processedBlocks: newProcessed,
          totalBlocks: newTotal,
          avgConfidence: updatedAvg,
          statusMessage: 'Processed block ${b.blockIdx + 1} on page ${b.pageIdx + 1}',
        );
        notifyListeners();

        // Forward to document state if callback is hooked
        onBBoxStreamed?.call(b.pageIdx, item);

      case WsBlockRetryFrame r:
        final key = r.blockKey;
        final currentCount = _state.blockRetryCounts[key] ?? 0;
        final newCounts = Map<String, int>.from(_state.blockRetryCounts);
        newCounts[key] = currentCount + 1;

        _state = _state.copyWith(
          stage: 'Refine / Quality Repair',
          statusMessage: 'Retrying low confidence block ${r.blockIdx + 1} (attempt ${r.attempt}, conf ${(r.confidence * 100).toStringAsFixed(1)}%)',
          blockRetryCounts: newCounts,
        );
        notifyListeners();

      case WsBlockRevisedFrame rev:
        final item = rev.toBBoxItem();
        final updatedRepaired = [..._state.repairedBlocks, item];

        _state = _state.copyWith(
          stage: 'Refine / Quality Repair',
          statusMessage: 'Repaired block ${rev.blockIdx + 1} on page ${rev.pageIdx + 1}',
          repairedBlocks: updatedRepaired,
        );
        notifyListeners();

        // Forward revised box to document state
        onBBoxStreamed?.call(rev.pageIdx, item);

      case WsPageCompleteFrame pageComp:
        final completed = Set<int>.from(_state.completedPages)..add(pageComp.pageIdx);
        _state = _state.copyWith(
          completedPages: completed,
          statusMessage: 'Completed page ${pageComp.pageIdx + 1}',
        );
        notifyListeners();

      case WsQualitySummaryFrame q:
        _state = _state.copyWith(
          qualitySummary: q.summary,
          avgConfidence: q.summary.avgConfidence,
          statusMessage: 'Quality target ${(q.summary.target * 100).round()}%: ${q.summary.repairedCount} repaired',
        );
        notifyListeners();

      case WsCancelledFrame c:
        _state = _state.copyWith(
          isProcessing: false,
          stage: 'Cancelled',
          percent: c.percent,
          statusMessage: c.status.isNotEmpty ? c.status : 'Job was cancelled',
        );
        notifyListeners();

      case WsUnknownFrame _:
        // Ignore unhandled frame types gracefully
        break;
    }
  }

  /// Handles raw JSON map from WebSocket
  void handleWsJson(Map<String, dynamic> json) {
    final frame = WsEnvelope.fromJson(json);
    handleWsFrame(frame);
  }

  /// Cancels active job
  void cancelJob() {
    if (!_state.isProcessing) return;
    _state = _state.copyWith(
      isProcessing: false,
      stage: 'Cancelled',
      statusMessage: 'Cancelled by user',
    );
    notifyListeners();
  }

  /// Completes active job successfully
  void completeJob({String message = 'Processing complete'}) {
    _state = _state.copyWith(
      isProcessing: false,
      percent: 100.0,
      stage: 'Complete',
      statusMessage: message,
    );
    notifyListeners();
  }

  /// Marks job as failed with error message
  void failJob(String error) {
    _state = _state.copyWith(
      isProcessing: false,
      stage: 'Error',
      statusMessage: error,
      warnings: [..._state.warnings, error],
    );
    notifyListeners();
  }

  /// Resets state to Idle
  void reset() {
    _state = const JobProgressState();
    notifyListeners();
  }
}
