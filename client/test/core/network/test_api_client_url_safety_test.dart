// Regression test for Sprint 3 / C-2 audit fix: ApiClient refuses plaintext
// HTTP for non-loopback hosts. Loopback is the documented local-trusted
// mode; any other host must use HTTPS to keep the bearer token confidential.

import 'package:flutter_test/flutter_test.dart';

import 'package:omniscribe_client/core/network/api_client.dart';

void main() {
  group('ApiClient C-2 base-url safety', () {
    test('accepts loopback plaintext http://', () {
      // Constructor does the validation, so this must not throw.
      ApiClient(baseUrl: 'http://127.0.0.1:8000');
      ApiClient(baseUrl: 'http://localhost:8000');
      ApiClient(baseUrl: 'http://[::1]:8000');
    });

    test('accepts https for any host', () {
      ApiClient(baseUrl: 'https://api.example.com');
      ApiClient(baseUrl: 'https://192.168.1.10:8000');
    });

    test('refuses plaintext http for non-loopback', () {
      expect(
        () => ApiClient(baseUrl: 'http://api.example.com'),
        throwsA(isA<ArgumentError>()),
      );
      expect(
        () => ApiClient(baseUrl: 'http://192.168.1.10:8000'),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('refuses non-http schemes', () {
      expect(
        () => ApiClient(baseUrl: 'ftp://example.com'),
        throwsA(isA<ArgumentError>()),
      );
    });
  });
}
