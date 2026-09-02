// WorkstationState's constructor intentionally wraps collection arguments with
// `List.unmodifiable` / `Map.unmodifiable` to enforce the immutability
// contract proven by the tests in the `Immutability (unmodifiable getters)`
// group below. That defensive copy means the constructor cannot be `const`,
// which trips `prefer_const_constructors` and `prefer_const_literals_to_
// create_immutables` for every test instantiation in this file. Silencing
// these two lints here is intentional and scoped.
// ignore_for_file: prefer_const_constructors, prefer_const_literals_to_create_immutables

import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/models/document_result.dart';
import 'package:omniscribe_client/data/providers/workstation_state.dart';

void main() {
  group('WorkstationState Construction & Defaults', () {
    test('default constructor provides sane initial defaults', () {
      final state = WorkstationState();

      expect(state.loadedBytes, isNull);
      expect(state.filename, isNull);
      expect(state.filePath, isNull);
      expect(state.pageCount, 0);
      expect(state.selectedPageIndex, 0);
      expect(state.pages, isEmpty);

      expect(state.selectedBBox, isNull);
      expect(state.hoveredBBox, isNull);
      expect(state.showBBoxes, isTrue);
      expect(state.showHeatmap, isTrue);
      expect(state.zoomScale, 1.0);
      expect(state.panOffset, Offset.zero);
      expect(state.filterKind, isNull);

      expect(state.isProcessing, isFalse);
      expect(state.activeJobId, isNull);
      expect(state.channelId, isNull);
      expect(state.percent, 0);
      expect(state.stage, 'Idle');
      expect(state.statusMessage, '');
      expect(state.warnings, isEmpty);
      expect(state.blockRetryCounts, isEmpty);
      expect(state.qualitySummary, isNull);
      expect(state.avgConfidence, isNull);
      expect(state.processedBlocks, 0);
      expect(state.totalBlocks, 0);
      expect(state.scoredBlocks, 0);
      expect(state.trustSummary, isNull);
      expect(state.error, isNull);
      expect(state.textArtifactId, isNull);
      expect(state.textArtifactToken, isNull);

      expect(state.hasDocument, isFalse);
      expect(state.currentPage, isNull);
      expect(state.currentPageBBoxes, isEmpty);
      expect(state.allBBoxes, isEmpty);
      expect(state.totalRetriesAttempted, 0);
      expect(state.repairedCount, 0);
      expect(state.percentInt, 0);
      expect(state.currentStageIndex, -1);
      expect(state.confidenceSummary, isNull);
    });
  });

  group('WorkstationState Getters', () {
    test('hasDocument requires loadedBytes or filePath (pages alone are not enough)', () {
      // loadedBytes alone => true
      expect(
        WorkstationState(loadedBytes: Uint8List.fromList([1, 2, 3])).hasDocument,
        isTrue,
      );
      // filePath alone => true
      expect(
        WorkstationState(filePath: '/path/to/doc.pdf').hasDocument,
        isTrue,
      );
      // both => true
      expect(
        WorkstationState(
          loadedBytes: Uint8List.fromList([1, 2, 3]),
          filePath: '/path/to/doc.pdf',
        ).hasDocument,
        isTrue,
      );
      // pages alone without loadedBytes/filePath => false (new contract)
      expect(
        WorkstationState(pages: [PageResult(page: 0)]).hasDocument,
        isFalse,
      );
      // fully empty => false
      expect(WorkstationState().hasDocument, isFalse);
    });

    test('currentPage returns page at selectedPageIndex or null if out of range', () {
      const page0 = PageResult(page: 0);
      const page1 = PageResult(page: 1);
      final state = WorkstationState(
        pages: [page0, page1],
        pageCount: 2,
        selectedPageIndex: 1,
      );

      expect(state.currentPage, equals(page1));

      final invalidState = state.copyWith(selectedPageIndex: 5);
      expect(invalidState.currentPage, isNull);
    });

    test('currentPageBBoxes filters by filterKind when present', () {
      const b1 = BBoxItem(
        blockId: 'b1',
        page: 0,
        block: 0,
        bbox: [0, 0, 1, 1],
        text: 'Heading',
        kind: 'heading',
      );
      const b2 = BBoxItem(
        blockId: 'b2',
        page: 0,
        block: 1,
        bbox: [0, 0, 1, 1],
        text: 'Paragraph',
        kind: 'paragraph',
      );

      final state = WorkstationState(
        pages: [
          PageResult(page: 0, bboxes: [b1, b2]),
        ],
        pageCount: 1,
        selectedPageIndex: 0,
      );

      expect(state.currentPageBBoxes, equals([b1, b2]));
      expect(state.allBBoxes, equals([b1, b2]));

      final filteredState = state.copyWith(filterKind: 'heading');
      expect(filteredState.currentPageBBoxes, equals([b1]));

      final allFilterState = state.copyWith(filterKind: 'all');
      expect(allFilterState.currentPageBBoxes, equals([b1, b2]));
    });

    test('confidenceSummary correctly computes stats across all scored boxes', () {
      const b1 = BBoxItem(
        blockId: 'b1',
        page: 0,
        block: 0,
        bbox: [0, 0, 1, 1],
        text: 'T1',
        confidence: 0.90,
      );
      const b2 = BBoxItem(
        blockId: 'b2',
        page: 0,
        block: 1,
        bbox: [0, 0, 1, 1],
        text: 'T2',
        confidence: 0.70,
      );
      const b3 = BBoxItem(
        blockId: 'b3',
        page: 1,
        block: 0,
        bbox: [0, 0, 1, 1],
        text: 'T3',
        confidence: null,
      );

      final state = WorkstationState(
        pages: [
          PageResult(page: 0, bboxes: [b1, b2]),
          PageResult(page: 1, bboxes: [b3]),
        ],
      );

      final summary = state.confidenceSummary;
      expect(summary, isNotNull);
      expect(summary!.count, 2);
      expect(summary.average, closeTo(0.80, 0.001));
      expect(summary.min, 0.70);
      expect(summary.max, 0.90);
      expect(summary.averagePercent, 80);
      expect(summary.minPercent, 70);
      expect(summary.maxPercent, 90);
    });

    test('totalRetriesAttempted and repairedCount compute accurate counts', () {
      const b1 = BBoxItem(
        blockId: 'b1',
        page: 0,
        block: 0,
        bbox: [0, 0, 1, 1],
        text: 'T1',
        revised: true,
      );

      final state = WorkstationState(
        pages: [
          PageResult(page: 0, bboxes: [b1]),
        ],
        blockRetryCounts: {'p0_b0': 2, 'p0_b1': 1},
        qualitySummary: const QualitySummary(
          scope: 'document',
          target: 0.85,
          avgConfidence: 0.92,
          repairedCount: 3,
          belowTargetCount: 1,
        ),
      );

      expect(state.totalRetriesAttempted, 3);
      expect(state.repairedCount, 3);
    });

    test('currentStageIndex maps stage name correctly', () {
      expect(WorkstationState(stage: 'Conversion').currentStageIndex, 0);
      expect(WorkstationState(stage: 'Detection').currentStageIndex, 1);
      expect(WorkstationState(stage: 'OCR').currentStageIndex, 2);
      expect(
        WorkstationState(stage: 'Refine / Quality Repair').currentStageIndex,
        3,
      );
      expect(WorkstationState(stage: 'Postprocess').currentStageIndex, 4);
      expect(WorkstationState(stage: 'Embedding').currentStageIndex, 5);
    });

    test('currentStageIndex returns -1 for non-pipeline stages', () {
      // Sentinel states outside the pipelineStages list should return -1
      expect(WorkstationState(stage: 'Idle').currentStageIndex, -1);
      expect(WorkstationState(stage: 'Complete').currentStageIndex, -1);
      expect(WorkstationState(stage: 'Warning').currentStageIndex, -1);
      expect(WorkstationState(stage: 'Error').currentStageIndex, -1);
      expect(WorkstationState(stage: 'Cancelled').currentStageIndex, -1);
      expect(WorkstationState(stage: 'UnknownStage').currentStageIndex, -1);
    });
  });

  group('WorkstationState Immutability (unmodifiable getters)', () {
    test('pages getter returns an unmodifiable list', () {
      final state = WorkstationState(pages: [PageResult(page: 0)]);

      // Reading is fine
      expect(state.pages.length, 1);
      expect(state.pages.first.page, 0);

      // Mutating the returned list must throw
      expect(
        () => state.pages.add(PageResult(page: 1)),
        throwsUnsupportedError,
      );
      expect(
        () => state.pages.clear(),
        throwsUnsupportedError,
      );
      expect(
        () => state.pages.removeAt(0),
        throwsUnsupportedError,
      );
    });

    test('warnings getter returns an unmodifiable list', () {
      final state = WorkstationState(warnings: ['warn-1', 'warn-2']);

      expect(state.warnings.length, 2);
      expect(state.warnings.first, 'warn-1');

      expect(
        () => state.warnings.add('warn-3'),
        throwsUnsupportedError,
      );
      expect(
        () => state.warnings.clear(),
        throwsUnsupportedError,
      );
    });

    test('blockRetryCounts getter returns an unmodifiable map', () {
      final state = WorkstationState(blockRetryCounts: {'p0_b0': 2});

      expect(state.blockRetryCounts['p0_b0'], 2);

      expect(
        () => state.blockRetryCounts['p1_b1'] = 1,
        throwsUnsupportedError,
      );
      expect(
        () => state.blockRetryCounts.remove('p0_b0'),
        throwsUnsupportedError,
      );
      expect(
        () => state.blockRetryCounts.clear(),
        throwsUnsupportedError,
      );
    });

    test('copyWith produces unmodifiable collections', () {
      final original = WorkstationState(
        pages: [PageResult(page: 0)],
        warnings: ['warn-1'],
        blockRetryCounts: {'p0_b0': 1},
      );

      // Pass new mutable collections into copyWith; they must be wrapped.
      final next = original.copyWith(
        pages: [PageResult(page: 0), PageResult(page: 1)],
        warnings: ['warn-2'],
        blockRetryCounts: {'p1_b0': 3},
      );

      expect(() => next.pages.add(PageResult(page: 2)), throwsUnsupportedError);
      expect(() => next.warnings.add('warn-3'), throwsUnsupportedError);
      expect(
        () => next.blockRetryCounts['k'] = 0,
        throwsUnsupportedError,
      );
    });
  });

  group('WorkstationState copyWith & Clear Flags', () {
    test('preserves untouched fields and overwrites specified values', () {
      final initial = WorkstationState(
        filename: 'doc.pdf',
        pageCount: 5,
        percent: 50,
        stage: 'OCR',
      );

      final updated = initial.copyWith(
        percent: 75,
        stage: 'Postprocess',
      );

      expect(updated.filename, 'doc.pdf');
      expect(updated.pageCount, 5);
      expect(updated.percent, 75);
      expect(updated.stage, 'Postprocess');
    });

    test('clear flags explicitly reset nullable fields to null', () {
      final initial = WorkstationState(
        loadedBytes: Uint8List.fromList([1, 2]),
        filename: 'test.pdf',
        filePath: '/test.pdf',
        selectedBBox: const BBoxItem(
          blockId: 'b1',
          page: 0,
          block: 0,
          bbox: [0, 0, 1, 1],
          text: 'T',
        ),
        hoveredBBox: const BBoxItem(
          blockId: 'b2',
          page: 0,
          block: 1,
          bbox: [0, 0, 1, 1],
          text: 'T',
        ),
        filterKind: 'heading',
        activeJobId: 'job-1',
        channelId: 'ch-1',
        qualitySummary: const QualitySummary(
          scope: 'document',
          target: 0.85,
          avgConfidence: 0.9,
          repairedCount: 1,
          belowTargetCount: 0,
        ),
        avgConfidence: 0.85,
        trustSummary: const TrustSummary(
          blockCount: 10,
          scoredCount: 10,
          flaggedCount: 0,
          average: 0.95,
        ),
        error: 'Some error',
        textArtifactId: 'art-1',
        textArtifactToken: 'tok-1',
      );

      final cleared = initial.copyWith(
        clearLoadedBytes: true,
        clearFilename: true,
        clearFilePath: true,
        clearSelectedBBox: true,
        clearHoveredBBox: true,
        clearFilterKind: true,
        clearActiveJobId: true,
        clearChannelId: true,
        clearQualitySummary: true,
        clearAvgConfidence: true,
        clearTrustSummary: true,
        clearError: true,
        clearTextArtifactId: true,
        clearTextArtifactToken: true,
      );

      expect(cleared.loadedBytes, isNull);
      expect(cleared.filename, isNull);
      expect(cleared.filePath, isNull);
      expect(cleared.selectedBBox, isNull);
      expect(cleared.hoveredBBox, isNull);
      expect(cleared.filterKind, isNull);
      expect(cleared.activeJobId, isNull);
      expect(cleared.channelId, isNull);
      expect(cleared.qualitySummary, isNull);
      expect(cleared.avgConfidence, isNull);
      expect(cleared.trustSummary, isNull);
      expect(cleared.error, isNull);
      expect(cleared.textArtifactId, isNull);
      expect(cleared.textArtifactToken, isNull);
    });
  });

  group('WorkstationState Equality & HashCode', () {
    test('instances with identical fields are equal and have matching hashCodes', () {
      final bytes1 = Uint8List.fromList([1, 2, 3]);
      final bytes2 = Uint8List.fromList([1, 2, 3]);

      final s1 = WorkstationState(
        loadedBytes: bytes1,
        filename: 'file.pdf',
        pageCount: 1,
        warnings: const ['warn1'],
        blockRetryCounts: const {'p0_b0': 1},
      );

      final s2 = WorkstationState(
        loadedBytes: bytes2,
        filename: 'file.pdf',
        pageCount: 1,
        warnings: const ['warn1'],
        blockRetryCounts: const {'p0_b0': 1},
      );

      expect(s1, equals(s2));
      expect(s1.hashCode, equals(s2.hashCode));
    });

    test('instances with different fields are not equal', () {
      final s1 = WorkstationState(percent: 10);
      final s2 = WorkstationState(percent: 20);

      expect(s1, isNot(equals(s2)));
    });

    test(
        'instances with equal blockRetryCounts but different insertion order are equal and have equal hashCodes',
        () {
      // Same entries, different insertion order
      final s1 = WorkstationState(
        blockRetryCounts: {'p0_b0': 1, 'p0_b1': 2, 'p0_b2': 3},
      );
      final s2 = WorkstationState(
        blockRetryCounts: {'p0_b2': 3, 'p0_b0': 1, 'p0_b1': 2},
      );

      expect(s1, equals(s2));
      expect(s1.hashCode, equals(s2.hashCode));

      // Mutating the original input map after construction must not affect equality
      final baseMap = <String, int>{'p0_b0': 1, 'p0_b1': 2};
      final s3 = WorkstationState(blockRetryCounts: baseMap);
      baseMap['p0_b2'] = 3;
      final s4 = WorkstationState(blockRetryCounts: {'p0_b0': 1, 'p0_b1': 2});
      expect(s3, equals(s4));
      expect(s3.hashCode, equals(s4.hashCode));
    });
  });
}
