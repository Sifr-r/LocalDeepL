import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/data/repositories/ocr_repository.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/presentation/workstation/canvas/bbox_inspector.dart';
import 'package:omniscribe_client/presentation/workstation/controls/page_strip.dart';
import 'package:omniscribe_client/presentation/workstation/controls/right_control_dock.dart';
import 'package:omniscribe_client/presentation/workstation/progress/bottom_progress_dock.dart';
import 'package:omniscribe_client/presentation/workstation/workstation_screen.dart';

class _MockOcrRepository extends Mock implements OcrRepository {}

const _invoiceBBox = BBoxItem(
  blockId: 'p0_b1',
  page: 0,
  block: 1,
  bbox: [0.1, 0.1, 0.5, 0.3],
  text: 'Invoice Title',
  confidence: 0.95,
);

void _loadDocumentWithBBox(WorkstationNotifier notifier) {
  notifier.loadDocument(
    Uint8List.fromList([1, 2, 3, 4]),
    'contract.pdf',
    pageCount: 3,
  );
  notifier.setBBoxes(0, const [_invoiceBBox]);
}

void main() {
  Widget buildWorkstationTest({
    List<Override> overrides = const [],
  }) {
    return ProviderScope(
      overrides: overrides,
      child: MaterialApp(
        theme: AppTheme.darkTheme,
        home: const Scaffold(
          body: WorkstationScreen(),
        ),
      ),
    );
  }

  setUpAll(() {
    registerFallbackValue(const ProcessSettings());
    registerFallbackValue(Uint8List(0));
  });

  group('WorkstationScreen Widget Tests', () {
    testWidgets('Renders initial dropzone when no document is loaded',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildWorkstationTest());
      await tester.pumpAndSettle();

      expect(find.text('OmniScribe'), findsOneWidget);
      expect(find.text('GPU-Accelerated Document Workstation'), findsOneWidget);
      expect(find.text('DOCUVERSE 2.0'), findsOneWidget);
      expect(find.text('Upload document for OCR processing'), findsOneWidget);
    });

    testWidgets(
        'Dropzone renders without overflow at narrow 800x600 viewport '
        '(regression for Phase A follow-up #1 — AuthRequiredBanner mounted '
        'in AppShell reduces available vertical space)',
        (WidgetTester tester) async {
      // Phase A follow-up #1: AuthRequiredBanner mounted above TabRibbon
      // reduces the workstation's available vertical space. The dropzone
      // must wrap in SingleChildScrollView so it scrolls rather than
      // overflows at small viewports.
      tester.view.physicalSize = const Size(800, 600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildWorkstationTest());
      await tester.pumpAndSettle();

      // No exception = no RenderFlex overflow. The dropzone content is
      // visible (it scrolls into view inside SingleChildScrollView).
      expect(tester.takeException(), isNull);
      expect(find.byType(Scrollable), findsWidgets,
          reason: 'dropzone must scroll when viewport is tight');
      expect(find.text('Upload document for OCR processing'), findsOneWidget);
    });

    testWidgets('Renders full split-pane viewport when document is loaded',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildWorkstationTest());
      await tester.pumpAndSettle();

      // Load sample doc
      final container = ProviderScope.containerOf(
          tester.element(find.byType(WorkstationScreen)));
      final notifier = container.read(workstationProvider.notifier);
      _loadDocumentWithBBox(notifier);

      await tester.pumpAndSettle();

      expect(find.text('Clear Document'), findsOneWidget);
      expect(find.text('Process Document'), findsOneWidget);
      expect(find.text('PAGES (3)'), findsOneWidget);
      // BottomProgressDock renders whenever a document is loaded.
      expect(find.byType(BottomProgressDock), findsOneWidget);
      expect(find.byType(RightControlDock), findsOneWidget);
      expect(find.byType(PageStrip), findsOneWidget);
    });

    testWidgets('Renders stacked layout when viewport is narrow',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildWorkstationTest());
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
          tester.element(find.byType(WorkstationScreen)));
      _loadDocumentWithBBox(container.read(workstationProvider.notifier));

      await tester.pumpAndSettle();

      // Stacked branch still surfaces the dock and page strip
      // in a scrollable column rather than a side-by-side Row.
      expect(find.byType(RightControlDock), findsOneWidget);
      expect(find.byType(PageStrip), findsOneWidget);
      expect(find.text('Process Document'), findsOneWidget);
    });

    testWidgets('Shows BBoxInspector once a bbox is selected',
        (WidgetTester tester) async {
      final ocrRepo = _MockOcrRepository();
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildWorkstationTest(
        overrides: [ocrRepositoryProvider.overrideWithValue(ocrRepo)],
      ));
      await tester.pumpAndSettle();

      final container = ProviderScope.containerOf(
          tester.element(find.byType(WorkstationScreen)));
      final notifier = container.read(workstationProvider.notifier);
      _loadDocumentWithBBox(notifier);
      notifier.selectBBox(_invoiceBBox);

      await tester.pumpAndSettle();

      expect(find.byType(BBoxInspector), findsOneWidget);
      expect(find.text('Bounding Box Inspector'), findsOneWidget);
      expect(find.text('Invoice Title'), findsWidgets);
    });
  });
}
