import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/presentation/shell/app_shell.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    const ProviderScope(
      child: OmniScribeApp(),
    ),
  );
}

class OmniScribeApp extends ConsumerStatefulWidget {
  const OmniScribeApp({super.key});

  @override
  ConsumerState<OmniScribeApp> createState() => _OmniScribeAppState();
}

class _OmniScribeAppState extends ConsumerState<OmniScribeApp> {
  @override
  void initState() {
    super.initState();
    // Kick off the initial config fetch once the notifier is available.
    Future.microtask(
      () => ref.read(settingsStateProvider.notifier).load(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final settings = ref.watch(settingsStateProvider);

    return MaterialApp(
      title: 'OmniScribe',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: settings.isDarkMode ? ThemeMode.dark : ThemeMode.light,
      home: const AppShell(),
    );
  }
}
