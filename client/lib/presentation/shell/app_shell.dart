import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/enums/app_tab.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/presentation/common/auth_required_banner.dart';
import 'package:omniscribe_client/presentation/features/extraction_screen.dart';
import 'package:omniscribe_client/presentation/features/glossary_screen.dart';
import 'package:omniscribe_client/presentation/features/transcription_screen.dart';
import 'package:omniscribe_client/presentation/features/translation_screen.dart';
import 'package:omniscribe_client/presentation/jobs/job_history_screen.dart';
import 'package:omniscribe_client/presentation/settings/settings_screen.dart';
import 'package:omniscribe_client/presentation/shell/shell_state.dart';
import 'package:omniscribe_client/presentation/shell/tab_ribbon.dart';
import 'package:omniscribe_client/presentation/workstation/modals/export_modal.dart';
import 'package:omniscribe_client/presentation/workstation/workstation_screen.dart';

class AppShell extends ConsumerWidget {
  const AppShell({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final activeTab = ref.watch(activeTabProvider);
    final colors = context.colors;

    Widget currentScreen;
    switch (activeTab) {
      case AppTab.workstation:
        currentScreen = const WorkstationScreen();
        break;
      case AppTab.translation:
        currentScreen = const TranslationScreen();
        break;
      case AppTab.transcription:
        currentScreen = const TranscriptionScreen();
        break;
      case AppTab.extraction:
        currentScreen = const ExtractionScreen();
        break;
      case AppTab.glossary:
        currentScreen = const GlossaryScreen();
        break;
      case AppTab.jobs:
        currentScreen = const JobHistoryScreen();
        break;
      case AppTab.settings:
        currentScreen = const SettingsScreen();
        break;
    }

    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.digit1, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.workstation;
        },
        const SingleActivator(LogicalKeyboardKey.digit2, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.translation;
        },
        const SingleActivator(LogicalKeyboardKey.digit3, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.transcription;
        },
        const SingleActivator(LogicalKeyboardKey.digit4, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.extraction;
        },
        const SingleActivator(LogicalKeyboardKey.digit5, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.glossary;
        },
        const SingleActivator(LogicalKeyboardKey.digit6, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.jobs;
        },
        const SingleActivator(LogicalKeyboardKey.digit7, control: true): () {
          ref.read(activeTabProvider.notifier).state = AppTab.settings;
        },
        const SingleActivator(LogicalKeyboardKey.keyS, control: true): () {
          final wsState = ref.read(workstationProvider);
          if (wsState.hasDocument) {
            ExportModal.show(context);
          }
        },
      },
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: colors.background,
          body: SafeArea(
            child: Column(
              children: [
                const AuthRequiredBanner(),
                const TabRibbon(),
                Expanded(child: currentScreen),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
