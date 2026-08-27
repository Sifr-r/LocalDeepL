import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/presentation/common/auth_required_banner.dart';

void main() {
  testWidgets('hides by default', (tester) async {
    await tester.pumpWidget(
      const ProviderScope(
        child: MaterialApp(home: Scaffold(body: AuthRequiredBanner())),
      ),
    );
    expect(find.text('Authentication required'), findsNothing);
  });

  testWidgets('shows when authRequiredProvider is true', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRequiredProvider.overrideWith((ref) => true),
        ],
        child: const MaterialApp(
          home: Scaffold(body: AuthRequiredBanner()),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('Authentication required'), findsOneWidget);
    expect(find.text('Open Settings'), findsOneWidget);
  });

  testWidgets('dismiss button clears the flag', (tester) async {
    final container = ProviderContainer(
      overrides: [authRequiredProvider.overrideWith((ref) => true)],
    );
    addTearDown(container.dispose);

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(
          home: Scaffold(body: AuthRequiredBanner()),
        ),
      ),
    );
    await tester.pump();
    expect(container.read(authRequiredProvider), isTrue);

    await tester.tap(find.byIcon(Icons.close));
    await tester.pump();
    expect(container.read(authRequiredProvider), isFalse);
  });
}
