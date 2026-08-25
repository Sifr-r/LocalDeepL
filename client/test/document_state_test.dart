import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/models/bbox_item.dart';
import 'package:omniscribe_client/state/document_state.dart';

void main() {
  group('DocumentStateNotifier Tests', () {
    late DocumentStateNotifier notifier;

    setUp(() {
      notifier = DocumentStateNotifier();
    });

    tearDown(() {
      notifier.dispose();
    });

    test('Initial state is empty', () {
      expect(notifier.state.hasDocument, isFalse);
      expect(notifier.state.pageCount, 0);
      expect(notifier.state.selectedPageIndex, 0);
      expect(notifier.state.selectedBBox, isNull);
    });

    test('loadDocument initializes pages and resets selection', () {
      final bytes = Uint8List.fromList([1, 2, 3, 4]);
      notifier.loadDocument(bytes, 'contract.pdf', pageCount: 3);

      expect(notifier.state.hasDocument, isTrue);
      expect(notifier.state.filename, 'contract.pdf');
      expect(notifier.state.pageCount, 3);
      expect(notifier.state.pages.length, 3);
      expect(notifier.state.selectedPageIndex, 0);
    });

    test('selectPage switches current page index', () {
      notifier.loadDocument(null, 'test.pdf', pageCount: 4);
      notifier.selectPage(2);

      expect(notifier.state.selectedPageIndex, 2);
    });

    test('addOrUpdateBBox inserts new box and updates existing', () {
      notifier.loadDocument(null, 'test.pdf', pageCount: 2);

      const box1 = BBoxItem(
        blockId: 'p0_b0',
        page: 0,
        block: 0,
        bbox: [0.1, 0.1, 0.5, 0.3],
        text: 'Initial block',
        confidence: 0.80,
      );
      notifier.addOrUpdateBBox(0, box1);

      expect(notifier.state.currentPageBBoxes.length, 1);
      expect(notifier.state.currentPageBBoxes.first.text, 'Initial block');

      // Update box1
      final updatedBox1 = box1.copyWith(
        text: 'Revised block',
        confidence: 0.96,
        revised: true,
      );
      notifier.addOrUpdateBBox(0, updatedBox1);

      expect(notifier.state.currentPageBBoxes.length, 1);
      expect(notifier.state.currentPageBBoxes.first.text, 'Revised block');
      expect(notifier.state.currentPageBBoxes.first.revised, isTrue);
      expect(notifier.state.currentPageBBoxes.first.confidence, 0.96);
    });

    test('selectBBox updates selected box', () {
      const box = BBoxItem(
        blockId: 'p0_b0',
        page: 0,
        block: 0,
        bbox: [0.1, 0.1, 0.5, 0.3],
        text: 'Selected block',
      );

      notifier.selectBBox(box);
      expect(notifier.state.selectedBBox, box);

      notifier.selectBBox(null);
      expect(notifier.state.selectedBBox, isNull);
    });

    test('Layer toggles update showBBoxes and showHeatmap', () {
      expect(notifier.state.showBBoxes, isTrue);
      notifier.toggleBBoxes();
      expect(notifier.state.showBBoxes, isFalse);

      expect(notifier.state.showHeatmap, isTrue);
      notifier.toggleHeatmap();
      expect(notifier.state.showHeatmap, isFalse);
    });

    test('Confidence summary computes average, min, max correctly', () {
      notifier.loadDocument(null, 'test.pdf', pageCount: 1);
      notifier.setBBoxes(0, [
        const BBoxItem(
          blockId: 'b1',
          page: 0,
          block: 0,
          bbox: [0, 0, 1, 1],
          text: 'One',
          confidence: 0.90,
        ),
        const BBoxItem(
          blockId: 'b2',
          page: 0,
          block: 1,
          bbox: [0, 0, 1, 1],
          text: 'Two',
          confidence: 0.70,
        ),
      ]);

      final summary = notifier.state.confidenceSummary;
      expect(summary, isNotNull);
      expect(summary!.average, 0.80);
      expect(summary.min, 0.70);
      expect(summary.max, 0.90);
      expect(summary.count, 2);
    });
  });
}
