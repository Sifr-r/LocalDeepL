import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';

import 'package:omniscribe_client/core/constants/api_constants.dart';
import 'package:omniscribe_client/core/network/api_client.dart';
import 'package:omniscribe_client/data/models/document_result.dart';
import 'package:omniscribe_client/data/models/job_record.dart';
import 'package:omniscribe_client/data/models/process_settings.dart';

/// Progress channel session credentials.
class ProgressSessionHandle {
  const ProgressSessionHandle({
    required this.channelId,
    required this.sessionToken,
  });

  final String channelId;
  final String sessionToken;
}

abstract class OcrRepository {
  /// Execute synchronous OCR, returning the resulting searchable PDF bytes and trust headers.
  Future<ProcessOcrResult> processOcrSync({
    required Uint8List fileBytes,
    required String filename,
    ProcessSettings? settings,
    String? progressChannel,
    String? progressToken,
    void Function(int sent, int total)? onSendProgress,
  });

  /// Submit an asynchronous OCR job to the worker queue.
  Future<AsyncSubmitResponse> processOcrAsync({
    required Uint8List fileBytes,
    required String filename,
    ProcessSettings? settings,
    String? progressChannel,
    String? progressToken,
    void Function(int sent, int total)? onSendProgress,
  });

  /// Query the status of an active or completed OCR job.
  Future<OcrJobStatusResponse> getOcrStatus(String jobId);

  /// Download the PDF output for a completed asynchronous OCR job.
  Future<Uint8List> getOcrResultBytes(String jobId, String token);

  /// Cancel a running or queued job.
  Future<bool> cancelJob(String jobId);

  /// Request a fresh WebSocket progress channel session handle.
  Future<ProgressSessionHandle> openProgressSession({String? clientId});

  /// Cancel an active progress channel.
  Future<bool> cancelProgressChannel(String channelId);

  /// Fetch text artifact content by ID with artifact bearer token.
  Future<String> getTextArtifact(String artifactId, String token);
}

class OcrRepositoryImpl implements OcrRepository {
  const OcrRepositoryImpl(this._apiClient);

  final ApiClient _apiClient;

  FormData _buildOcrFormData({
    required Uint8List fileBytes,
    required String filename,
    ProcessSettings? settings,
    String? progressChannel,
    String? progressToken,
  }) {
    final s = settings ?? ProcessSettings.defaultSettings();
    final map = <String, dynamic>{
      'file': MultipartFile.fromBytes(fileBytes, filename: filename),
      'model': s.model,
      'api_base': s.apiBase,
      if (s.apiKey.isNotEmpty) 'api_key': s.apiKey,
      'pipeline_mode': s.pipelineMode.value,
      'dense_mode': s.denseMode.value,
      'spellcheck': s.spellcheck.value,
      'preprocess_pages': s.preprocessPages.toString(),
      'orientation_detection': s.orientationDetection.toString(),
      'deskew': s.deskew.toString(),
      'denoise': s.denoise.toString(),
      'normalize_contrast': s.normalizeContrast.toString(),
      'crop_cleanup': s.cropCleanup.toString(),
    };

    if (s.pages != null && s.pages!.isNotEmpty) {
      map['pages'] = s.pages;
    }
    if (s.documentProcessors.isNotEmpty) {
      map['document_processors'] =
          s.documentProcessors.map((p) => p.value).join(',');
    }
    if (progressChannel != null && progressChannel.isNotEmpty) {
      map['progress_channel'] = progressChannel;
    }
    if (progressToken != null && progressToken.isNotEmpty) {
      map['progress_token'] = progressToken;
    }
    if (s.qualityLoopEnabled != null) {
      map['quality_loop_enabled'] = s.qualityLoopEnabled.toString();
    }
    if (s.qualityTarget != null) {
      map['quality_target'] = s.qualityTarget.toString();
    }
    if (s.qualityMaxRetries != null) {
      map['quality_max_retries'] = s.qualityMaxRetries.toString();
    }

    return FormData.fromMap(map);
  }

  @override
  Future<ProcessOcrResult> processOcrSync({
    required Uint8List fileBytes,
    required String filename,
    ProcessSettings? settings,
    String? progressChannel,
    String? progressToken,
    void Function(int sent, int total)? onSendProgress,
  }) async {
    final formData = _buildOcrFormData(
      fileBytes: fileBytes,
      filename: filename,
      settings: settings,
      progressChannel: progressChannel,
      progressToken: progressToken,
    );

    final response = await _apiClient.postMultipartBytes(
      ApiConstants.processSync,
      formData: formData,
      onSendProgress: onSendProgress,
    );

    final headers = response.headers;
    final trustRaw = headers[ApiConstants.headerDocumentTrust];
    final trustSummary = TrustSummary.tryParseHeader(trustRaw);

    return ProcessOcrResult(
      pdfBytes: response.data,
      headers: headers,
      trustSummary: trustSummary,
      textArtifactId: headers[ApiConstants.headerTextArtifactId],
      textArtifactToken: headers[ApiConstants.headerTextArtifactToken],
    );
  }

  @override
  Future<AsyncSubmitResponse> processOcrAsync({
    required Uint8List fileBytes,
    required String filename,
    ProcessSettings? settings,
    String? progressChannel,
    String? progressToken,
    void Function(int sent, int total)? onSendProgress,
  }) async {
    final formData = _buildOcrFormData(
      fileBytes: fileBytes,
      filename: filename,
      settings: settings,
      progressChannel: progressChannel,
      progressToken: progressToken,
    );

    final response = await _apiClient.postMultipart<Map<String, dynamic>>(
      ApiConstants.processAsync,
      formData: formData,
      onSendProgress: onSendProgress,
    );

    return AsyncSubmitResponse.fromJson(response.data);
  }

  @override
  Future<OcrJobStatusResponse> getOcrStatus(String jobId) async {
    final json = await _apiClient.get<Map<String, dynamic>>(
      ApiConstants.processStatus(jobId),
    );
    return OcrJobStatusResponse.fromJson(json);
  }

  @override
  Future<Uint8List> getOcrResultBytes(String jobId, String token) async {
    return _apiClient.getBytes(
      ApiConstants.jobResult(jobId),
      queryParameters: {'token': token},
      headers: {'Authorization': 'Bearer $token'},
    );
  }

  @override
  Future<bool> cancelJob(String jobId) async {
    final json = await _apiClient.post<Map<String, dynamic>>(
      ApiConstants.cancelJob(jobId),
    );
    return json['cancelled'] as bool? ?? false;
  }

  @override
  Future<ProgressSessionHandle> openProgressSession({String? clientId}) async {
    final json = await _apiClient.post<Map<String, dynamic>>(
      ApiConstants.progressSession,
      data: <String, dynamic>{'client_id': clientId ?? ''},
    );
    return ProgressSessionHandle(
      channelId: json['channel_id']?.toString() ?? '',
      sessionToken: json['session_token']?.toString() ?? '',
    );
  }

  @override
  Future<bool> cancelProgressChannel(String channelId) async {
    final json = await _apiClient.post<Map<String, dynamic>>(
      ApiConstants.cancelProgress(channelId),
    );
    return json['cancelled'] as bool? ?? false;
  }

  @override
  Future<String> getTextArtifact(String artifactId, String token) async {
    final bytes = await _apiClient.getBytes(
      ApiConstants.textArtifact(artifactId),
      headers: {'Authorization': 'Bearer $token'},
    );
    return utf8.decode(bytes);
  }
}
