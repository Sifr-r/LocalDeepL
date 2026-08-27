import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/core/websocket/ws_client.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/models/document_result.dart';
import 'package:omniscribe_client/data/models/job_record.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/models/ws_frames.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/data/repositories/ocr_repository.dart';

class _MockOcrRepository extends Mock implements OcrRepository {}

class _MockWsClient extends Mock implements WsClient {}

void main() {
  late _MockOcrRepository ocrRepo;
  late _MockWsClient wsClient;
  late StreamController<WsEnvelope> wsStreamController;

  setUpAll(() {
    registerFallbackValue(Uint8List(0));
    registerFallbackValue(const ProcessSettings());
  });

  setUp(() {
    ocrRepo = _MockOcrRepository();
    wsClient = _MockWsClient();
    wsStreamController = StreamController<WsEnvelope>.broadcast();

    when(() => wsClient.stream).thenAnswer((_) => wsStreamController.stream);
    when(() => wsClient.connect(
          channelId: any(named: 'channelId'),
          sessionToken: any(named: 'sessionToken'),
        )).thenAnswer((_) async {});
    when(() => wsClient.cancelChannel()).thenReturn(null);
    when(() => wsClient.disconnect()).thenAnswer((_) async {});
    when(() => ocrRepo.cancelProgressChannel(any()))
        .thenAnswer((_) async => true);
  });

  tearDown(() {
    wsStreamController.close();
  });

  ProviderContainer makeContainer() {
    return ProviderContainer(
      overrides: [
        ocrRepositoryProvider.overrideWithValue(ocrRepo),
        wsClientProvider.overrideWithValue(wsClient),
      ],
    );
  }

  group('WorkstationNotifier.build', () {
    test('returns empty WorkstationState before any interactions', () {
      final container = makeContainer();
      addTearDown(container.dispose);

      final state = container.read(workstationProvider);

      expect(state.hasDocument, isFalse);
      expect(state.isProcessing, isFalse);
      expect(state.pages, isEmpty);
      expect(state.error, isNull);
    });
  });

  group('Document & Viewport Operations', () {
    test('loadDocument initializes pages and resets viewport/progress', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      final bytes = Uint8List.fromList([0x25, 0x50, 0x44, 0x46]);
      notifier.loadDocument(bytes, 'sample.pdf', pageCount: 3);

      final state = container.read(workstationProvider);
      expect(state.hasDocument, isTrue);
      expect(state.filename, 'sample.pdf');
      expect(state.pageCount, 3);
      expect(state.pages.length, 3);
      expect(state.selectedPageIndex, 0);
      expect(state.zoomScale, 1.0);
      expect(state.panOffset, Offset.zero);
      expect(state.showBBoxes, isTrue);
      expect(state.showHeatmap, isTrue);
    });

    test('selectPage switches page and clears selections', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 3);
      notifier.selectBBox(const BBoxItem(
        blockId: 'b1',
        page: 0,
        block: 0,
        bbox: [0, 0, 1, 1],
        text: 'text',
      ));
      notifier.hoverBBox(const BBoxItem(
        blockId: 'b2',
        page: 0,
        block: 1,
        bbox: [0, 0, 1, 1],
        text: 'text',
      ));

      notifier.selectPage(1);

      final state = container.read(workstationProvider);
      expect(state.selectedPageIndex, 1);
      expect(state.selectedBBox, isNull);
      expect(state.hoveredBBox, isNull);
    });

    test('setBBoxes and addOrUpdateBBox update page elements', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 2);

      const box1 = BBoxItem(
        blockId: 'p0_b0',
        page: 0,
        block: 0,
        bbox: [0.1, 0.1, 0.9, 0.3],
        text: 'Initial text',
      );
      notifier.setBBoxes(0, [box1]);

      var state = container.read(workstationProvider);
      expect(state.pages[0].bboxes.length, 1);
      expect(state.pages[0].bboxes.first.text, 'Initial text');

      // Update existing box
      const updatedBox1 = BBoxItem(
        blockId: 'p0_b0',
        page: 0,
        block: 0,
        bbox: [0.1, 0.1, 0.9, 0.3],
        text: 'Revised text',
        revised: true,
      );
      notifier.addOrUpdateBBox(0, updatedBox1);

      state = container.read(workstationProvider);
      expect(state.pages[0].bboxes.length, 1);
      expect(state.pages[0].bboxes.first.text, 'Revised text');
      expect(state.pages[0].bboxes.first.revised, isTrue);

      // Add a new box on page 0
      const box2 = BBoxItem(
        blockId: 'p0_b1',
        page: 0,
        block: 1,
        bbox: [0.1, 0.4, 0.9, 0.6],
        text: 'Second box',
      );
      notifier.addOrUpdateBBox(0, box2);

      state = container.read(workstationProvider);
      expect(state.pages[0].bboxes.length, 2);
    });

    test('viewport modifiers (zoom, pan, reset, toggle) work as expected', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.setZoomScale(2.5);
      expect(container.read(workstationProvider).zoomScale, 2.5);

      notifier.setPanOffset(const Offset(100, 200));
      expect(
        container.read(workstationProvider).panOffset,
        const Offset(100, 200),
      );

      notifier.toggleBBoxes(false);
      expect(container.read(workstationProvider).showBBoxes, isFalse);

      notifier.toggleHeatmap(false);
      expect(container.read(workstationProvider).showHeatmap, isFalse);

      notifier.resetViewport();
      final state = container.read(workstationProvider);
      expect(state.zoomScale, 1.0);
      expect(state.panOffset, Offset.zero);
    });

    test('clearDocument resets to empty state', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 2);
      expect(container.read(workstationProvider).hasDocument, isTrue);

      await notifier.clearDocument();
      expect(container.read(workstationProvider).hasDocument, isFalse);
    });

    test('setBBoxes with negative page index is a no-op', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 2);

      // Seed a known-good bbox on page 0
      const seed = BBoxItem(
        blockId: 'p0_b0',
        page: 0,
        block: 0,
        bbox: [0.1, 0.1, 0.9, 0.3],
        text: 'seed',
      );
      notifier.setBBoxes(0, [seed]);
      final before = container.read(workstationProvider);

      // Negative page index must not throw and must not change state
      expect(
        () => notifier.setBBoxes(-1, const [
          BBoxItem(
            blockId: 'p_neg_b0',
            page: -1,
            block: 0,
            bbox: [0, 0, 1, 1],
            text: 'should-not-appear',
          ),
        ]),
        returnsNormally,
      );

      final after = container.read(workstationProvider);
      expect(after.pages.length, before.pages.length);
      expect(after.pageCount, before.pageCount);
      expect(after.pages[0].bboxes.length, before.pages[0].bboxes.length);
      expect(after.pages[0].bboxes.first.text, 'seed');
    });

    test('addOrUpdateBBox with negative page index is a no-op', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 2);
      final before = container.read(workstationProvider);

      // Negative page index must not throw and must not change state
      expect(
        () => notifier.addOrUpdateBBox(
          -1,
          const BBoxItem(
            blockId: 'p_neg_b0',
            page: -1,
            block: 0,
            bbox: [0, 0, 1, 1],
            text: 'should-not-appear',
          ),
        ),
        returnsNormally,
      );

      final after = container.read(workstationProvider);
      expect(after.pages.length, before.pages.length);
      expect(after.pageCount, before.pageCount);
      // Every pre-existing page should still be unchanged
      for (var i = 0; i < before.pages.length; i++) {
        expect(after.pages[i].bboxes, before.pages[i].bboxes);
      }
    });

    test('selectPage is no-op when pageCount is 0', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      // No document loaded; pageCount defaults to 0
      expect(container.read(workstationProvider).pageCount, 0);

      notifier.selectPage(0);
      expect(container.read(workstationProvider).selectedPageIndex, 0);

      notifier.selectPage(2);
      expect(container.read(workstationProvider).selectedPageIndex, 0);

      notifier.selectPage(-1);
      expect(container.read(workstationProvider).selectedPageIndex, 0);
    });
  });

  group('WebSocket Frame Handling', () {
    test('handleWsFrame processes ProgressFrame', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.handleWsFrame(const ProgressFrame(
        status: 'Detecting layout...',
        percent: 30,
        stage: 'Detection',
      ));

      final state = container.read(workstationProvider);
      expect(state.percent, 30);
      expect(state.stage, 'Detection');
      expect(state.statusMessage, 'Detecting layout...');
      expect(state.warnings, isEmpty);
    });

    test('handleWsFrame records warnings from ProgressFrame', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.handleWsFrame(const ProgressFrame(
        status: 'Low contrast on page 1',
        percent: 40,
        stage: 'Detection',
        warning: true,
      ));

      final state = container.read(workstationProvider);
      expect(state.warnings, contains('Low contrast on page 1'));
    });

    test('handleWsFrame processes BlockCompleteFrame, BlockRetryFrame, BlockRevisedFrame', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 1);

      // 1. Block complete
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 0,
        bbox: [0.1, 0.1, 0.9, 0.3],
        text: 'OCR text',
        kind: 'paragraph',
        confidence: 0.50,
      ));

      var state = container.read(workstationProvider);
      expect(state.processedBlocks, 1);
      expect(state.avgConfidence, 0.50);
      expect(state.pages[0].bboxes.length, 1);

      // 2. Block retry
      notifier.handleWsFrame(const BlockRetryFrame(
        pageIdx: 0,
        blockIdx: 0,
        attempt: 1,
        confidence: 0.50,
        target: 0.85,
      ));

      state = container.read(workstationProvider);
      expect(state.blockRetryCounts['p0_b0'], 1);
      expect(state.stage, 'Refine / Quality Repair');

      // 3. Block revised
      notifier.handleWsFrame(const BlockRevisedFrame(
        pageIdx: 0,
        blockIdx: 0,
        attempt: 1,
        bbox: [0.1, 0.1, 0.9, 0.3],
        text: 'Repaired OCR text',
        kind: 'paragraph',
        confidence: 0.95,
      ));

      state = container.read(workstationProvider);
      expect(state.pages[0].bboxes.first.text, 'Repaired OCR text');
      expect(state.pages[0].bboxes.first.revised, isTrue);
      expect(state.pages[0].bboxes.first.confidence, 0.95);
    });

    test('handleWsFrame processes QualitySummaryFrame and CancelledFrame', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.handleWsFrame(const QualitySummaryFrame(
        scope: 'document',
        target: 0.85,
        avgConfidence: 0.94,
        repairedCount: 2,
        belowTargetCount: 0,
      ));

      var state = container.read(workstationProvider);
      expect(state.qualitySummary, isNotNull);
      expect(state.qualitySummary!.repairedCount, 2);
      expect(state.avgConfidence, 0.94);

      notifier.handleWsFrame(const CancelledFrame(
        status: 'Cancelled by server',
        percent: 50,
      ));

      state = container.read(workstationProvider);
      expect(state.isProcessing, isFalse);
      expect(state.stage, 'Cancelled');
      expect(state.statusMessage, 'Cancelled by server');
    });

    test('BlockCompleteFrame with null confidence does not bias avg', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 1);

      // Block 0: confidence = 1.0 -> avg = 1.0
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 0,
        bbox: [0, 0, 1, 1],
        text: 'a',
        kind: 'paragraph',
        confidence: 1.0,
      ));

      var state = container.read(workstationProvider);
      expect(state.processedBlocks, 1);
      expect(state.scoredBlocks, 1);
      expect(state.avgConfidence, 1.0);

      // Block 1: null confidence -> avg unchanged, scoredBlocks unchanged
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 1,
        bbox: [0, 0, 1, 1],
        text: 'b',
        kind: 'paragraph',
        confidence: null,
      ));

      state = container.read(workstationProvider);
      expect(state.processedBlocks, 2);
      expect(state.scoredBlocks, 1);
      expect(state.avgConfidence, 1.0);

      // Block 2: null confidence -> still avg=1.0
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 2,
        bbox: [0, 0, 1, 1],
        text: 'c',
        kind: 'paragraph',
        confidence: null,
      ));

      state = container.read(workstationProvider);
      expect(state.processedBlocks, 3);
      expect(state.scoredBlocks, 1);
      expect(state.avgConfidence, 1.0);
    });

    test('interleaved scored and unscored blocks compute correct average', () {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List(0), 'sample.pdf', pageCount: 1);

      // Sequence: 0.8, null, 0.6, null, null
      // Scored values: 0.8, 0.6 -> avg should be 0.7
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 0,
        bbox: [0, 0, 1, 1],
        text: 'a',
        kind: 'paragraph',
        confidence: 0.8,
      ));
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 1,
        bbox: [0, 0, 1, 1],
        text: 'b',
        kind: 'paragraph',
        confidence: null,
      ));
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 2,
        bbox: [0, 0, 1, 1],
        text: 'c',
        kind: 'paragraph',
        confidence: 0.6,
      ));
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 3,
        bbox: [0, 0, 1, 1],
        text: 'd',
        kind: 'paragraph',
        confidence: null,
      ));
      notifier.handleWsFrame(const BlockCompleteFrame(
        pageIdx: 0,
        blockIdx: 4,
        bbox: [0, 0, 1, 1],
        text: 'e',
        kind: 'paragraph',
        confidence: null,
      ));

      final state = container.read(workstationProvider);
      expect(state.processedBlocks, 5);
      expect(state.scoredBlocks, 2);
      expect(state.avgConfidence, closeTo(0.7, 1e-9));
    });
  });

  group('OCR Pipeline Execution', () {
    test('processOcrSync executes successfully and populates trust headers', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      final inputBytes = Uint8List.fromList([1, 2, 3]);
      final outputBytes = Uint8List.fromList([4, 5, 6]);
      notifier.loadDocument(inputBytes, 'doc.pdf', pageCount: 1);

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-1',
                sessionToken: 'tok-1',
              ));

      when(() => ocrRepo.processOcrSync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => ProcessOcrResult(
            pdfBytes: outputBytes,
            headers: const {},
            trustSummary: const TrustSummary(
              blockCount: 5,
              scoredCount: 5,
              flaggedCount: 0,
              average: 0.98,
            ),
          ));

      await notifier.processOcrSync();

      final state = container.read(workstationProvider);
      expect(state.isProcessing, isFalse);
      expect(state.percent, 100);
      expect(state.stage, 'Complete');
      expect(state.loadedBytes, outputBytes);
      expect(state.trustSummary?.average, 0.98);
      expect(state.error, isNull);
    });

    test('processOcrSync populates error on failure', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenThrow(Exception('Backend unavailable'));

      when(() => ocrRepo.processOcrSync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenThrow(Exception('OCR server crashed'));

      await expectLater(
        notifier.processOcrSync(),
        throwsA(isA<Exception>()),
      );

      final state = container.read(workstationProvider);
      expect(state.isProcessing, isFalse);
      expect(state.stage, 'Error');
      expect(state.error, contains('OCR server crashed'));
    });

    test('processOcrAsync opens session and submits async job', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-async',
                sessionToken: 'tok-async',
              ));

      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => const AsyncSubmitResponse(
            jobId: 'job-999',
            status: 'queued',
          ));

      await notifier.processOcrAsync();

      final state = container.read(workstationProvider);
      expect(state.activeJobId, 'job-999');
      expect(state.channelId, 'ch-async');
      expect(state.error, isNull);
    });

    test('cancelOcr cancels active progress and job', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.cancelProgressChannel('ch-1'))
          .thenAnswer((_) async => true);
      when(() => ocrRepo.cancelJob('job-1')).thenAnswer((_) async => true);

      // Simulate an in-flight OCR run by directly stamping the state with
      // channelId, activeJobId, and isProcessing=true. (processOcrSync/Async
      // both flip isProcessing to false on success, which is the post-fix
      // expected behavior.)
      notifier.state = notifier.state.copyWith(
        channelId: 'ch-1',
        activeJobId: 'job-1',
        isProcessing: true,
      );

      await notifier.cancelOcr();

      final state = container.read(workstationProvider);
      expect(state.isProcessing, isFalse);
      expect(state.stage, 'Cancelled');
      verify(() => wsClient.cancelChannel()).called(1);
    });

    test('processOcrSync success closes WS and cancels channel', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2, 3]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-sync-cleanup',
                sessionToken: 'tok-sync-cleanup',
              ));

      when(() => ocrRepo.processOcrSync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => ProcessOcrResult(
            pdfBytes: Uint8List.fromList([9, 9]),
            headers: const {},
            trustSummary: const TrustSummary(
              blockCount: 1,
              scoredCount: 1,
              flaggedCount: 0,
              average: 0.9,
            ),
          ));

      await notifier.processOcrSync();

      verify(() => wsClient.disconnect()).called(1);
      verify(() => ocrRepo.cancelProgressChannel('ch-sync-cleanup')).called(1);
    });

    test('processOcrAsync failure closes WS and cancels channel', () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-async-fail',
                sessionToken: 'tok-async-fail',
              ));

      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenThrow(Exception('Submission failed'));

      await expectLater(
        notifier.processOcrAsync(),
        throwsA(isA<Exception>()),
      );

      verify(() => wsClient.disconnect()).called(1);
      verify(() => ocrRepo.cancelProgressChannel('ch-async-fail')).called(1);
    });

    test('processOcrAsync success sets isProcessing false and stage Complete',
        () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-async-ok',
                sessionToken: 'tok-async-ok',
              ));

      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => const AsyncSubmitResponse(
            jobId: 'job-async-ok',
            status: 'queued',
          ));

      await notifier.processOcrAsync();

      final state = container.read(workstationProvider);
      expect(state.isProcessing, isFalse);
      expect(state.stage, 'Complete');
      expect(state.activeJobId, 'job-async-ok');
    });

    test(
        'processOcrAsync success cleans up WS + channel even when submission succeeds',
        () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-async-success-cleanup',
                sessionToken: 'tok-async-success-cleanup',
              ));

      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => const AsyncSubmitResponse(
            jobId: 'job-cleanup',
            status: 'queued',
          ));

      await notifier.processOcrAsync();

      verify(() => wsClient.disconnect()).called(1);
      verify(() => ocrRepo.cancelProgressChannel('ch-async-success-cleanup'))
          .called(1);
    });

    test('dispose triggers full cleanup', () async {
      final container = makeContainer();
      final notifier = container.read(workstationProvider.notifier);

      // Set channelId via ConnectedFrame; state.channelId will be non-null
      notifier.handleWsFrame(const ConnectedFrame(channelId: 'ch-dispose'));

      // Explicit dispose triggers ref.onDispose -> _cleanup (async, fire-and-forget)
      container.dispose();

      // Yield to the microtask queue so async _cleanup() runs to completion
      // before we verify mock interactions.
      await Future<void>.delayed(Duration.zero);

      verify(() => wsClient.disconnect()).called(1);
      verify(() => ocrRepo.cancelProgressChannel('ch-dispose')).called(1);
    });

    test(
        'processOcrSync after a stale async run clears activeJobId/channelId',
        () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      // ---- 1. Stale async run: sets activeJobId, channelId ----
      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-stale',
                sessionToken: 'tok-stale',
              ));
      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => const AsyncSubmitResponse(
            jobId: 'job-stale',
            status: 'queued',
          ));

      await notifier.processOcrAsync();
      var state = container.read(workstationProvider);
      expect(state.activeJobId, 'job-stale');
      expect(state.channelId, 'ch-stale');

      // ---- 2. Sync run must clear stale activeJobId/channelId/trustSummary ----
      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-fresh',
                sessionToken: 'tok-fresh',
              ));
      when(() => ocrRepo.processOcrSync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => ProcessOcrResult(
            pdfBytes: Uint8List.fromList([7, 7]),
            headers: const {},
            trustSummary: const TrustSummary(
              blockCount: 2,
              scoredCount: 2,
              flaggedCount: 0,
              average: 0.95,
            ),
          ));

      await notifier.processOcrSync();

      state = container.read(workstationProvider);
      expect(state.activeJobId, isNull);
      expect(state.channelId, 'ch-fresh');
      expect(state.trustSummary?.average, 0.95);
    });

    test(
        'processOcrAsync after a stale sync run clears channelId/trustSummary',
        () async {
      final container = makeContainer();
      addTearDown(container.dispose);
      final notifier = container.read(workstationProvider.notifier);

      notifier.loadDocument(Uint8List.fromList([1, 2]), 'doc.pdf');

      // ---- 1. Stale sync run: sets channelId + trustSummary ----
      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-stale-sync',
                sessionToken: 'tok-stale-sync',
              ));
      when(() => ocrRepo.processOcrSync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => ProcessOcrResult(
            pdfBytes: Uint8List.fromList([8, 8]),
            headers: const {},
            trustSummary: const TrustSummary(
              blockCount: 1,
              scoredCount: 1,
              flaggedCount: 0,
              average: 0.85,
            ),
          ));

      await notifier.processOcrSync();
      var state = container.read(workstationProvider);
      expect(state.channelId, 'ch-stale-sync');
      expect(state.trustSummary?.average, 0.85);

      // ---- 2. Async run must clear stale channelId/trustSummary ----
      when(() => ocrRepo.openProgressSession(clientId: any(named: 'clientId')))
          .thenAnswer((_) async => const ProgressSessionHandle(
                channelId: 'ch-fresh-async',
                sessionToken: 'tok-fresh-async',
              ));
      when(() => ocrRepo.processOcrAsync(
            fileBytes: any(named: 'fileBytes'),
            filename: any(named: 'filename'),
            settings: any(named: 'settings'),
            progressChannel: any(named: 'progressChannel'),
            progressToken: any(named: 'progressToken'),
            onSendProgress: any(named: 'onSendProgress'),
          )).thenAnswer((_) async => const AsyncSubmitResponse(
            jobId: 'job-fresh',
            status: 'queued',
          ));

      await notifier.processOcrAsync();

      state = container.read(workstationProvider);
      // trustSummary is cleared (replaced by null), channelId is the new session's
      expect(state.trustSummary, isNull);
      expect(state.channelId, 'ch-fresh-async');
      expect(state.activeJobId, 'job-fresh');
    });
  });
}
