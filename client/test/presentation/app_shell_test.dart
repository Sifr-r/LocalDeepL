import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/presentation/features/extraction_screen.dart';
import 'package:omniscribe_client/presentation/features/glossary_screen.dart';
import 'package:omniscribe_client/presentation/features/transcription_screen.dart';
import 'package:omniscribe_client/presentation/features/translation_screen.dart';
import 'package:omniscribe_client/presentation/jobs/job_history_screen.dart';
import 'package:omniscribe_client/presentation/settings/settings_screen.dart';
import 'package:omniscribe_client/presentation/shell/app_shell.dart';
import 'package:omniscribe_client/presentation/workstation/workstation_screen.dart';

void main() {
  Widget buildAppShell() {
    return ProviderScope(
      child: MaterialApp(
        theme: AppTheme.darkTheme,
        home: const Scaffold(
          body: AppShell(),
        ),
      ),
    );
  }

  group('Individual Screens Tests', () {
    testWidgets('WorkstationScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: WorkstationScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('OmniScribe'), findsOneWidget);
    });

    testWidgets('TranslationScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: TranslationScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TranslationScreen), findsOneWidget);
    });

    testWidgets('TranscriptionScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: TranscriptionScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TranscriptionScreen), findsOneWidget);
    });

    testWidgets('GlossaryScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: GlossaryScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(GlossaryScreen), findsOneWidget);
    });

    testWidgets('ExtractionScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: ExtractionScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(ExtractionScreen), findsOneWidget);
    });

    testWidgets('JobHistoryScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: JobHistoryScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(JobHistoryScreen), findsOneWidget);
    });

    testWidgets('SettingsScreen renders cleanly', (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(
        ProviderScope(
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(body: SettingsScreen()),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SettingsScreen), findsOneWidget);
    });
  });

  group('AppShell & Tab Navigation Tests', () {
    testWidgets('Renders OmniScribe brand and default Workstation tab',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      expect(find.text('OmniScribe'), findsWidgets);
      expect(find.text('DOCUVERSE 2.0'), findsOneWidget);
    });

    testWidgets('Switches to Translation tab when Translation is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Translation');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Neural Translation Engine'), findsOneWidget);
    });

    testWidgets('Switches to Transcription tab when Transcription is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Transcription');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Voice & Audio Transcription'), findsOneWidget);
    });

    testWidgets('Switches to Glossary tab when Glossary is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Glossary');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Terminology Glossary'), findsOneWidget);
    });

    testWidgets('Switches to Extraction tab when Extraction is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Extraction');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Structured Information Extraction'), findsOneWidget);
    });

    testWidgets('Switches to Job History tab when Job History is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Job History');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Job Execution History'), findsOneWidget);
    });

    testWidgets('Switches to Settings tab when Settings is tapped',
        (WidgetTester tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      await tester.pumpWidget(buildAppShell());
      await tester.pumpAndSettle();

      final tab = find.widgetWithText(InkWell, 'Settings');
      await tester.tap(tab);
      await tester.pumpAndSettle();

      expect(find.text('Settings & Configuration'), findsOneWidget);
    });
  });
}
