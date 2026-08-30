import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:omniscribe_client/data/models/process_settings.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/config_repository.dart';
import 'package:omniscribe_client/main.dart';

class _MockConfigRepository extends Mock implements ConfigRepository {}

void main() {
  testWidgets('OmniScribe app boots without throwing', (tester) async {
    final mockConfig = _MockConfigRepository();
    when(() => mockConfig.getConfig()).thenAnswer(
      (_) async => RuntimeConfig.fromJson(const {}),
    );
    when(() => mockConfig.getModelsForProvider(any())).thenAnswer(
      (_) async => ['allenai/olmocr-2-7b'],
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          configRepositoryProvider.overrideWithValue(mockConfig),
        ],
        child: const OmniScribeApp(),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byType(MaterialApp), findsWidgets);
  });
}
