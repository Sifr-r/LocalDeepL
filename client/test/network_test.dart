import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/core/network/api_exceptions.dart';

void main() {
  group('ApiClient Error Translation Tests', () {
    late ApiClient apiClient;

    setUp(() {
      apiClient = ApiClient();
    });

    test('Translates 400 bad request to ValidationException', () async {
      final dio = apiClient.rawDio;
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: Response(
                  requestOptions: options,
                  statusCode: 400,
                  data: {'error': 'bad_request', 'detail': 'Missing parameter'},
                ),
              ),
            );
          },
        ),
      );

      expect(
        () => apiClient.get<dynamic>('/test'),
        throwsA(
          isA<ValidationException>()
              .having((e) => e.statusCode, 'statusCode', 400)
              .having((e) => e.error, 'error', 'bad_request'),
        ),
      );
    });

    test('Translates 401 unauthorized to UnauthorizedException', () async {
      final dio = apiClient.rawDio;
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: Response(
                  requestOptions: options,
                  statusCode: 401,
                  data: {'error': 'unauthorized', 'detail': 'Invalid API Key'},
                ),
              ),
            );
          },
        ),
      );

      expect(
        () => apiClient.get<dynamic>('/test'),
        throwsA(
          isA<UnauthorizedException>()
              .having((e) => e.statusCode, 'statusCode', 401)
              .having((e) => e.message, 'message', 'Invalid API Key'),
        ),
      );
    });

    test('Translates 503 circuit_open to CircuitOpenException', () async {
      final dio = apiClient.rawDio;
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                response: Response(
                  requestOptions: options,
                  statusCode: 503,
                  data: {
                    'error': 'circuit_open',
                    'detail': 'LLM endpoint circuit breaker is open',
                  },
                ),
              ),
            );
          },
        ),
      );

      expect(
        () => apiClient.get<dynamic>('/test'),
        throwsA(
          isA<CircuitOpenException>()
              .having((e) => e.statusCode, 'statusCode', 503)
              .having((e) => e.error, 'error', 'circuit_open'),
        ),
      );
    });

    test('Translates connection timeout to NetworkException', () async {
      final dio = apiClient.rawDio;
      dio.interceptors.clear();
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            handler.reject(
              DioException(
                requestOptions: options,
                type: DioExceptionType.connectionTimeout,
                message: 'Connection timed out',
              ),
            );
          },
        ),
      );

      expect(
        () => apiClient.get<dynamic>('/test'),
        throwsA(
          isA<NetworkException>().having((e) => e.isTimeout, 'isTimeout', isTrue),
        ),
      );
    });
  });
}
