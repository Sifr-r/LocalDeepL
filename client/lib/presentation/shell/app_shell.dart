import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/features/extraction_screen.dart';
import 'package:omniscribe_client/presentation/features/glossary_screen.dart';
import 'package:omniscribe_client/presentation/features/transcription_screen.dart';
import 'package:omniscribe_client/presentation/features/translation_screen.dart';
import 'package:omniscribe_client/presentation/jobs/job_history_screen.dart';
import 'package:omniscribe_client/presentation/providers/provider_modal.dart';
import 'package:omniscribe_client/presentation/settings/settings_screen.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/workstation/workstation_screen.dart';

class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key});

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

class _AppShellState extends ConsumerState<AppShell> {
  int _selectedTabIndex = 0;

  final List<Map<String, dynamic>> _tabs = [
    {
      'title': 'Workstation',
      'icon': Icons.space_dashboard_outlined,
      'selectedIcon': Icons.space_dashboard
    },
    {
      'title': 'Translation',
      'icon': Icons.translate_outlined,
      'selectedIcon': Icons.translate
    },
    {
      'title': 'Transcription',
      'icon': Icons.mic_outlined,
      'selectedIcon': Icons.mic
    },
    {
      'title': 'Glossary',
      'icon': Icons.menu_book_outlined,
      'selectedIcon': Icons.menu_book
    },
    {
      'title': 'Extraction',
      'icon': Icons.schema_outlined,
      'selectedIcon': Icons.schema
    },
    {
      'title': 'Job History',
      'icon': Icons.history_outlined,
      'selectedIcon': Icons.history
    },
    {
      'title': 'Settings',
      'icon': Icons.settings_outlined,
      'selectedIcon': Icons.settings
    },
  ];

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsStateProvider);
    final tokens = context.docuVerse;

    final screens = [
      const WorkstationScreen(),
      const TranslationScreen(),
      const TranscriptionScreen(),
      const GlossaryScreen(),
      const ExtractionScreen(),
      const JobHistoryScreen(),
      const SettingsScreen(),
    ];

    return Container(
      color: tokens.app,
      child: Column(
        children: [
          Container(
            height: 60,
            decoration: BoxDecoration(
              color: tokens.card,
              border: Border(bottom: BorderSide(color: tokens.border, width: 1)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: SafeArea(
            child: Row(
              children: [
                // App Brand / Logo
                InkWell(
                  onTap: () => setState(() => _selectedTabIndex = 0),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(6),
                        decoration: BoxDecoration(
                          color: tokens.brand,
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: const Icon(Icons.document_scanner,
                            size: 18, color: Colors.white),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        'OmniScribe',
                        style: TextStyle(
                          fontSize: 17,
                          fontWeight: FontWeight.bold,
                          color: tokens.foreground,
                          letterSpacing: -0.3,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 24),

                // Navigation Tabs
                Expanded(
                  child: SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: List.generate(_tabs.length, (index) {
                        final tab = _tabs[index];
                        final isSelected = _selectedTabIndex == index;
                        return InkWell(
                          onTap: () =>
                              setState(() => _selectedTabIndex = index),
                          borderRadius: BorderRadius.circular(6),
                          child: Container(
                            margin: const EdgeInsets.only(right: 4),
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 8),
                            decoration: BoxDecoration(
                              color: isSelected
                                  ? tokens.brand.withValues(alpha: 0.12)
                                  : Colors.transparent,
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: isSelected
                                    ? tokens.brand.withValues(alpha: 0.3)
                                    : Colors.transparent,
                              ),
                            ),
                            child: Row(
                              children: [
                                Icon(
                                  isSelected
                                      ? tab['selectedIcon'] as IconData
                                      : tab['icon'] as IconData,
                                  size: 16,
                                  color: isSelected
                                      ? tokens.brand
                                      : tokens.foregroundMuted,
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  tab['title'] as String,
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: isSelected
                                        ? FontWeight.w600
                                        : FontWeight.normal,
                                    color: isSelected
                                        ? tokens.brand
                                        : tokens.foregroundMuted,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }),
                    ),
                  ),
                ),

                // Right Utility Actions
                Row(
                  children: [
                    // Active Provider Badge
                    InkWell(
                      onTap: () => ProviderModal.show(context),
                      borderRadius: BorderRadius.circular(4),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 4, vertical: 2),
                        child: DocuVerseBadge(
                          text: settings.activeProviderId.toUpperCase(),
                          variant: DocuVerseBadgeVariant.brand,
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),

                    // Server Health Status Indicator (runtime — not tracked in SettingsState yet)
                    const DocuVerseBadge(
                      text: 'Offline',
                      variant: DocuVerseBadgeVariant.danger,
                      hasDot: true,
                    ),
                    const SizedBox(width: 12),

                    // Dark / Light Theme Toggle
                    IconButton(
                      icon: Icon(
                        settings.isDarkMode
                            ? Icons.light_mode_outlined
                            : Icons.dark_mode_outlined,
                        size: 18,
                        color: tokens.foregroundMuted,
                      ),
                      tooltip: settings.isDarkMode
                          ? 'Switch to Light Mode'
                          : 'Switch to Dark Mode',
                      splashRadius: 18,
                      onPressed: () => ref
                          .read(settingsStateProvider.notifier)
                          .toggleDarkMode(),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
        Expanded(
          child: screens[_selectedTabIndex],
        ),
      ],
    ),
  );
}
}
