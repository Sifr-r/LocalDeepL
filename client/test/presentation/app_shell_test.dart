import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/enums/app_tab.dart';
import 'package:omniscribe_client/core/enums/server_health.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/presentation/shell/app_shell.dart';
import 'package:omniscribe_client/presentation/shell/shell_state.dart';

void main() {
  Widget buildAppShell({
    AppTab initialTab = AppTab.workstation,
    ServerHealth serverStatus = ServerHealth.online,
  }) {
    return ProviderScope(
      overrides: [
        activeTabProvider.overrideWith((ref) => initialTab),
        serverHealthProvider.overrideWith(
          (ref) => ServerHealthNotifier()
            ..state = ServerHealthState(
              status: serverStatus,
              latencyMs: 25,
            ),
        ),
      ],
      child: MaterialApp(
        theme: AppTheme.darkTheme,
        home: const AppShell(),
      ),
    );
  }

  group('AppShell & TabRibbon Tests', () {
    testWidgets('Renders OmniScribe brand, v2.0 badge, and default Workstation view', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      expect(find.text('OmniScribe'), findsOneWidget);
      expect(find.text('v2.0'), findsOneWidget);
      expect(find.text('Document Workstation'), findsOneWidget);
    });

    testWidgets('Switches to Translation tab when Translation tab button is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      expect(find.text('Document Workstation'), findsOneWidget);

      await tester.tap(find.text('Translation'));
      await tester.pumpAndSettle();

      expect(find.text('Translation Workbench'), findsOneWidget);
    });

    testWidgets('Switches to Transcription tab when Transcription tab is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      await tester.tap(find.text('Transcription'));
      await tester.pumpAndSettle();

      expect(find.text('Audio & Video Transcription'), findsOneWidget);
    });

    testWidgets('Switches to Extraction tab when Extraction tab is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      await tester.tap(find.text('Extraction'));
      await tester.pumpAndSettle();

      expect(find.text('Schema & Entity Extraction'), findsOneWidget);
    });

    testWidgets('Switches to Glossary tab when Glossary tab is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      await tester.tap(find.text('Glossary'));
      await tester.pumpAndSettle();

      expect(find.text('Glossary & Translation Memories'), findsOneWidget);
    });

    testWidgets('Switches to Jobs tab when Jobs tab is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      await tester.tap(find.text('Jobs'));
      await tester.pumpAndSettle();

      expect(find.text('Job Execution History'), findsOneWidget);
    });

    testWidgets('Switches to Settings tab when Settings tab is tapped', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell());
      await tester.pump();

      await tester.tap(find.text('Settings'));
      await tester.pumpAndSettle();

      expect(find.text('System Configuration'), findsOneWidget);
    });

    testWidgets('ServerHealthBadge displays status correctly', (WidgetTester tester) async {
      await tester.pumpWidget(buildAppShell(serverStatus: ServerHealth.online));
      await tester.pump();

      expect(find.text('Online'), findsOneWidget);
      expect(find.text('25ms'), findsOneWidget);
    });
  });
}
