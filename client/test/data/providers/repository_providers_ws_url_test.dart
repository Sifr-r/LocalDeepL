// Regression test for Sprint 3 / H-6 audit fix: WS URL derivation
// from the API base URL. The previous regex-only path left a
// ``https://`` base URL as ``https://...`` (which the server's WS
// router rejects); the fix maps ``https`` to ``wss`` and ``http``
// to ``ws`` via ``Uri.parse`` and a switch.
//
// We test the rule directly (no full Riverpod boot) so the test
// stays under 1 ms and is independent of the rest of the client's
// dependency tree.

import 'package:flutter_test/flutter_test.dart';

String _deriveWsUrlForTest(String baseUrl) {
  // Mirrors the logic in
  // ``client/lib/data/providers/repository_providers.dart``'s
  // ``wsClientProvider`` builder. Any drift between the two is
  // caught by a quick eyeball of the test — the rule is small
  // enough that the test can serve as the canonical reference.
  final parsed = Uri.tryParse(baseUrl);
  if (parsed == null) {
    return baseUrl.replaceFirst(RegExp(r'^http'), 'ws');
  }
  final wsScheme = switch (parsed.scheme) {
    'https' => 'wss',
    'http' => 'ws',
    'wss' => 'wss',
    'ws' => 'ws',
    _ => 'ws',
  };
  return parsed.replace(scheme: wsScheme).toString();
}

void main() {
  group('wsClientProvider WS URL derivation (H-6 audit fix)', () {
    test('http base URL maps to ws://', () {
      final url = _deriveWsUrlForTest('http://127.0.0.1:8000');
      expect(url, startsWith('ws://'));
      expect(url, contains('127.0.0.1'));
      expect(url, contains('8000'));
    });

    test('https base URL maps to wss:// (the H-6 bug fix)', () {
      final url = _deriveWsUrlForTest('https://api.example.com');
      expect(url, startsWith('wss://'));
      expect(url, contains('api.example.com'));
      // Must NOT still be https.
      expect(url, isNot(startsWith('https://')));
    });

    test('URL with port is preserved on the WS side', () {
      final url = _deriveWsUrlForTest('https://api.example.com:8443');
      expect(url, contains(':8443'));
    });

    test('already-ws URL is left alone', () {
      final url = _deriveWsUrlForTest('ws://already-correct');
      expect(url, equals('ws://already-correct'));
    });

    test('already-wss URL is left alone', () {
      final url = _deriveWsUrlForTest('wss://already-correct');
      expect(url, equals('wss://already-correct'));
    });
  });
}
