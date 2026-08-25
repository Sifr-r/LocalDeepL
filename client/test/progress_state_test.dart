import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/models/quality_summary.dart';
import 'package:omniscribe_client/models/ws_envelope.dart';
import 'package:omniscribe_client/state/progress_state.dart';

void main() {
  group('ProgressStateNotifier Tests', () {
    late ProgressStateNotifier notifier;

    setUp(() {
      notifier = ProgressStateNotifier();
    });

    tearDown(() {
      notifier.dispose();
    });

    test('Initial state is idle', () {
      expect(notifier.state.isProcessing, isFalse);
      expect(notifier.state.stage, 'Idle');
      expect(notifier.state.percent, 0.0);
    });

    test('startJob transitions to processing and conversion stage', () {
      notifier.startJob('job_123', 'ws_channel');

      expect(notifier.state.isProcessing, isTrue);
      expect(notifier.state.activeJobId, 'job_123');
      expect(notifier.state.channelId, 'ws_channel');
      expect(notifier.state.stage, 'Conversion');
      expect(notifier.state.percent, 0.0);
    });

    test('handleWsFrame processes ProgressFrame', () {
      notifier.startJob('job_123', 'ws_channel');

      notifier.handleWsFrame(const WsProgressFrame(
        status: 'Detecting bounding boxes...',
        percent: 35.0,
        stage: 'Detection',
      ));

      expect(notifier.state.percent, 35.0);
      expect(notifier.state.stage, 'Detection');
      expect(notifier.state.statusMessage, 'Detecting bounding boxes...');
    });

    test('handleWsFrame processes block_complete and updates running average confidence', () {
      notifier.startJob('job_123', 'ws_channel');

      notifier.handleWsFrame(const WsBlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 0,
        bbox: [0, 0, 1, 1],
        text: 'Hello',
        kind: 'paragraph',
        confidence: 0.80,
      ));

      expect(notifier.state.processedBlocks, 1);
      expect(notifier.state.avgConfidence, 0.80);

      notifier.handleWsFrame(const WsBlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 1,
        bbox: [0, 0, 1, 1],
        text: 'World',
        kind: 'paragraph',
        confidence: 1.00,
      ));

      expect(notifier.state.processedBlocks, 2);
      expect(notifier.state.avgConfidence, closeTo(0.90, 0.001));
    });

    test('handleWsFrame processes block_retry and block_revised', () {
      notifier.startJob('job_123', 'ws_channel');

      notifier.handleWsFrame(const WsBlockRetryFrame(
        pageIdx: 0,
        blockIdx: 2,
        attempt: 1,
        confidence: 0.50,
        target: 0.85,
      ));

      expect(notifier.state.blockRetryCounts['p0_b2'], 1);
      expect(notifier.state.totalRetriesAttempted, 1);

      notifier.handleWsFrame(const WsBlockRevisedFrame(
        pageIdx: 0,
        blockIdx: 2,
        attempt: 1,
        bbox: [0, 0, 1, 1],
        text: 'Repaired text',
        kind: 'paragraph',
        confidence: 0.95,
      ));

      expect(notifier.state.repairedBlocks.length, 1);
      expect(notifier.state.repairedBlocks.first.revised, isTrue);
      expect(notifier.state.repairedCount, 1);
    });

    test('cancelJob transitions to Cancelled', () {
      notifier.startJob('job_123', 'ws_channel');
      notifier.cancelJob();

      expect(notifier.state.isProcessing, isFalse);
      expect(notifier.state.stage, 'Cancelled');
    });

    test('completeJob transitions to Complete at 100%', () {
      notifier.startJob('job_123', 'ws_channel');
      notifier.completeJob(message: 'Finished successfully');

      expect(notifier.state.isProcessing, isFalse);
      expect(notifier.state.percent, 100.0);
      expect(notifier.state.stage, 'Complete');
      expect(notifier.state.statusMessage, 'Finished successfully');
    });
  });
}
