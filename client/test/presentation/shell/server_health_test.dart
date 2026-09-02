import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:omniscribe_client/core/enums/server_health.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/presentation/shell/server_health_badge.dart';
import 'package:omniscribe_client/presentation/shell/shell_state.dart';

class _MockApiClient extends Mock implements ApiClient {}

void main() {
  late _MockApiClient mockClient;

  setUp(() {
    mockClient = _MockApiClient();
  });

  group('ServerHealthNotifier', () {
    test('checkHealth sets online when API call succeeds', () async {
      when(() => mockClient.get<dynamic>('/api/health')).thenAnswer(
        (_) async => const ApiResponse(
          data: {'status': 'ok'},
          statusCode: 200,
          headers: {},
        ),
      );

      final notifier = ServerHealthNotifier(mockClient);
      await notifier.checkHealth();

      expect(notifier.state.status, ServerHealth.online);
      expect(notifier.state.latencyMs, isNotNull);
      expect(notifier.state.error, isNull);
    });

    test('checkHealth sets offline when API call fails', () async {
      when(() => mockClient.get<dynamic>('/api/health')).thenThrow(
        Exception('Connection refused'),
      );

      final notifier = ServerHealthNotifier(mockClient);
      await notifier.checkHealth();

      expect(notifier.state.status, ServerHealth.offline);
      expect(notifier.state.latencyMs, isNull);
      expect(notifier.state.error, contains('Connection refused'));
    });

    test('checkHealth returns early when apiClient is null', () async {
      final notifier = ServerHealthNotifier(null);
      final beforeState = notifier.state;

      await notifier.checkHealth();

      expect(notifier.state.status, beforeState.status);
    });
  });

  group('ServerHealthBadge', () {
    testWidgets('tap triggers checkHealth via serverHealthProvider', (tester) async {
      when(() => mockClient.get<dynamic>('/api/health')).thenAnswer(
        (_) async => const ApiResponse(
          data: {'status': 'healthy'},
          statusCode: 200,
          headers: {},
        ),
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            apiClientProvider.overrideWithValue(mockClient),
          ],
          child: MaterialApp(
            theme: AppTheme.darkTheme,
            home: const Scaffold(
              body: ServerHealthBadge(),
            ),
          ),
        ),
      );

      expect(find.byType(ServerHealthBadge), findsOneWidget);

      await tester.tap(find.byType(ServerHealthBadge));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      verify(() => mockClient.get<dynamic>('/api/health')).called(1);
    });
  });
}
