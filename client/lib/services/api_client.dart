import 'dart:convert';
import 'dart:typed_data';
import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode, this.detail});

  final String message;
  final int? statusCode;
  final String? detail;

  @override
  String toString() => 'ApiException: $message (status: $statusCode, detail: $detail)';
}

class NetworkException implements Exception {
  NetworkException(this.message);
  final String message;

  @override
  String toString() => 'NetworkException: $message';
}

class ApiClient {
  ApiClient({
    this.baseUrl = 'http://127.0.0.1:8000',
    http.Client? httpClient,
  }) : _client = httpClient ?? http.Client();

  String baseUrl;
  final http.Client _client;
  String? authToken;

  Uri _buildUri(String path, [Map<String, dynamic>? queryParams]) {
    final cleanPath = path.startsWith('/') ? path : '/$path';
    final normalizedBase = baseUrl.endsWith('/') ? baseUrl.substring(0, baseUrl.length - 1) : baseUrl;
    final urlString = '$normalizedBase/api$cleanPath';
    final uri = Uri.parse(urlString);

    if (queryParams != null && queryParams.isNotEmpty) {
      final stringParams = queryParams.map((key, value) => MapEntry(key, value.toString()));
      return uri.replace(queryParameters: stringParams);
    }
    return uri;
  }

  Map<String, String> _buildHeaders([Map<String, String>? extraHeaders]) {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };
    if (authToken != null && authToken!.isNotEmpty) {
      headers['Authorization'] = 'Bearer $authToken';
    }
    if (extraHeaders != null) {
      headers.addAll(extraHeaders);
    }
    return headers;
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? queryParams, Map<String, String>? headers}) async {
    try {
      final uri = _buildUri(path, queryParams);
      final res = await _client.get(uri, headers: _buildHeaders(headers)).timeout(const Duration(seconds: 15));
      return _handleResponse(res);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw NetworkException('GET $path failed: $e');
    }
  }

  Future<dynamic> post(String path, {dynamic body, Map<String, dynamic>? queryParams, Map<String, String>? headers}) async {
    try {
      final uri = _buildUri(path, queryParams);
      final encodedBody = body != null ? jsonEncode(body) : null;
      final res = await _client.post(uri, headers: _buildHeaders(headers), body: encodedBody).timeout(const Duration(seconds: 45));
      return _handleResponse(res);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw NetworkException('POST $path failed: $e');
    }
  }

  Future<dynamic> delete(String path, {Map<String, dynamic>? queryParams, Map<String, String>? headers}) async {
    try {
      final uri = _buildUri(path, queryParams);
      final res = await _client.delete(uri, headers: _buildHeaders(headers)).timeout(const Duration(seconds: 15));
      return _handleResponse(res);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw NetworkException('DELETE $path failed: $e');
    }
  }

  Future<Uint8List> getBytes(String path, {Map<String, dynamic>? queryParams, Map<String, String>? headers}) async {
    try {
      final uri = _buildUri(path, queryParams);
      final customHeaders = _buildHeaders(headers)..remove('Content-Type');
      final res = await _client.get(uri, headers: customHeaders).timeout(const Duration(seconds: 60));
      if (res.statusCode >= 200 && res.statusCode < 300) {
        return res.bodyBytes;
      }
      throw ApiException('Failed to download file with status ${res.statusCode}', statusCode: res.statusCode);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw NetworkException('getBytes $path failed: $e');
    }
  }

  Future<dynamic> postMultipart(
    String path, {
    Map<String, String>? fields,
    List<http.MultipartFile>? files,
    Map<String, dynamic>? queryParams,
    Map<String, String>? headers,
  }) async {
    try {
      final uri = _buildUri(path, queryParams);
      final req = http.MultipartRequest('POST', uri);
      final customHeaders = _buildHeaders(headers)..remove('Content-Type');
      req.headers.addAll(customHeaders);

      if (fields != null) {
        req.fields.addAll(fields);
      }
      if (files != null) {
        req.files.addAll(files);
      }

      final streamedRes = await req.send().timeout(const Duration(seconds: 60));
      final res = await http.Response.fromStream(streamedRes);
      return _handleResponse(res);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw NetworkException('POST multipart $path failed: $e');
    }
  }

  dynamic _handleResponse(http.Response res) {
    final status = res.statusCode;
    if (status >= 200 && status < 300) {
      if (res.body.isEmpty) return null;
      try {
        return jsonDecode(res.body);
      } catch (_) {
        return res.body;
      }
    }

    String message = 'Request failed with status $status';
    String? detail;

    try {
      final errorJson = jsonDecode(res.body) as Map<String, dynamic>;
      message = errorJson['message'] as String? ?? errorJson['error'] as String? ?? message;
      detail = errorJson['detail']?.toString();
    } catch (_) {
      if (res.body.isNotEmpty) {
        message = res.body;
      }
    }

    throw ApiException(message, statusCode: status, detail: detail);
  }
}
