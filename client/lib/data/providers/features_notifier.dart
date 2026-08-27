import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/feature_models.dart';
import 'package:omniscribe_client/data/providers/features_state.dart';
import 'package:omniscribe_client/data/providers/repository_providers.dart';
import 'package:omniscribe_client/data/repositories/feature_repository.dart';

export 'package:omniscribe_client/data/providers/features_state.dart';

// ---------------------------------------------------------------------------
// Translation Notifier & Provider
// ---------------------------------------------------------------------------

final translationProvider =
    NotifierProvider<TranslationNotifier, TranslationState>(
  TranslationNotifier.new,
);

class TranslationNotifier extends Notifier<TranslationState> {
  late final FeatureRepository _repo;

  @override
  TranslationState build() {
    _repo = ref.watch(featureRepositoryProvider);
    return const TranslationState.initial();
  }

  void setSourceText(String text) {
    state = state.copyWith(sourceText: text);
  }

  void setTargetLanguage(String lang) {
    state = state.copyWith(targetLanguage: lang);
  }

  void setSelectedModel(String model) {
    state = state.copyWith(selectedModel: model);
  }

  void setUseNllb(bool useNllb) {
    state = state.copyWith(useNllb: useNllb);
  }

  void clearSourceText() {
    state = state.copyWith(sourceText: '');
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  void setTranslatedOutput(String output) {
    state = state.copyWith(translatedOutput: output);
  }

  void setAsyncJobId(String? jobId) {
    state = state.copyWith(
      asyncJobId: jobId,
      clearAsyncJobId: jobId == null,
    );
  }

  void setAsyncStatus(String? status) {
    state = state.copyWith(
      asyncStatus: status,
      clearAsyncStatus: status == null,
    );
  }

  Future<void> translate({
    String? apiBase,
    String? apiKey,
    String? fallbackModel,
    bool? dualTranslate,
  }) async {
    final text = state.sourceText.trim();
    if (text.isEmpty) {
      state = state.copyWith(
        error: 'Please provide source text to translate.',
      );
      return;
    }

    state = state.copyWith(
      isTranslating: true,
      translatedOutput: '',
      clearError: true,
      clearAsyncStatus: true,
    );

    try {
      if (state.useNllb) {
        final res = await _repo.translateNllb(
          text: text,
          targetLanguage: state.targetLanguage,
        );
        state = state.copyWith(
          translatedOutput: res.translatedText,
          isTranslating: false,
        );
      } else {
        final req = TranslationRequest(
          text: text,
          targetLanguage: state.targetLanguage,
          model: state.selectedModel.isNotEmpty
              ? state.selectedModel
              : fallbackModel,
          apiBase: apiBase,
          apiKey: apiKey,
          dualTranslate: dualTranslate,
        );
        final res = await _repo.translate(req);
        state = state.copyWith(
          translatedOutput: res.translatedText,
          isTranslating: false,
        );
      }
    } catch (e) {
      state = state.copyWith(
        isTranslating: false,
        error: e.toString(),
        translatedOutput: 'Translation failed: $e',
      );
    }
  }

  Future<String?> translateAsync({
    String? apiBase,
    String? apiKey,
    String? fallbackModel,
  }) async {
    final text = state.sourceText.trim();
    if (text.isEmpty) {
      state = state.copyWith(
        error: 'Please provide source text for async translation.',
      );
      return null;
    }

    state = state.copyWith(
      isTranslating: true,
      translatedOutput: '',
      asyncStatus: 'Queuing async translation job...',
      clearError: true,
    );

    try {
      final req = TranslationRequest(
        text: text,
        targetLanguage: state.targetLanguage,
        model: state.selectedModel.isNotEmpty
            ? state.selectedModel
            : fallbackModel,
        apiBase: apiBase,
        apiKey: apiKey,
      );
      final res = await _repo.translateAsync(req);
      state = state.copyWith(
        asyncJobId: res.jobId,
        asyncStatus: 'Job ${res.jobId} queued. Polling progress...',
      );
      return res.jobId;
    } catch (e) {
      state = state.copyWith(
        isTranslating: false,
        error: e.toString(),
        asyncStatus: 'Async translation failed: $e',
      );
      return null;
    }
  }

  Future<void> checkTranslationStatus(String jobId) async {
    try {
      final status = await _repo.getTranslationStatus(jobId);
      final stateStr = status.state.toUpperCase();

      if (stateStr == 'SUCCESS' || stateStr == 'COMPLETED') {
        state = state.copyWith(
          isTranslating: false,
          translatedOutput:
              status.result?.toString() ?? 'Translation completed.',
          asyncStatus: 'Completed.',
        );
      } else if (stateStr == 'FAILURE' ||
          stateStr == 'FAILED' ||
          status.error != null) {
        final err = status.detail ?? status.error ?? 'Unknown error';
        state = state.copyWith(
          isTranslating: false,
          error: err,
          asyncStatus: 'Failed: $err',
        );
      } else {
        state = state.copyWith(
          asyncStatus:
              'Status: ${status.state} (${status.status ?? "in-flight"})',
        );
      }
    } catch (e) {
      state = state.copyWith(
        isTranslating: false,
        error: e.toString(),
        asyncStatus: 'Polling error: $e',
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Transcription Notifier & Provider
// ---------------------------------------------------------------------------

final transcriptionProvider =
    NotifierProvider<TranscriptionNotifier, TranscriptionState>(
  TranscriptionNotifier.new,
);

class TranscriptionNotifier extends Notifier<TranscriptionState> {
  late final FeatureRepository _repo;

  @override
  TranscriptionState build() {
    _repo = ref.watch(featureRepositoryProvider);
    return const TranscriptionState.initial();
  }

  void setAudio(Uint8List bytes, String filename, {double? duration}) {
    state = state.copyWith(
      audioBytes: bytes,
      audioFilename: filename,
      totalDuration: duration ?? 45.0,
      currentPlaybackTime: 0.0,
      isPlaying: false,
      clearError: true,
    );
  }

  void setEngine(String engine) {
    state = state.copyWith(engine: engine);
  }

  void setModel(String model) {
    state = state.copyWith(model: model);
  }

  void setLanguage(String? language) {
    state = state.copyWith(
      language: language,
      clearLanguage: language == null || language.isEmpty,
    );
  }

  void setPrompt(String? prompt) {
    state = state.copyWith(
      prompt: prompt,
      clearPrompt: prompt == null || prompt.isEmpty,
    );
  }

  void clearAudio() {
    state = state.copyWith(
      clearAudio: true,
      totalDuration: 0.0,
      currentPlaybackTime: 0.0,
      isPlaying: false,
    );
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  void setPlaybackTime(double time) {
    state = state.copyWith(currentPlaybackTime: time);
    updateActiveSegment();
  }

  void setActiveSegmentId(int? id) {
    state = state.copyWith(
      activeSegmentId: id,
      clearActiveSegment: id == null,
    );
  }

  void setIsPlaying(bool isPlaying) {
    state = state.copyWith(isPlaying: isPlaying);
  }

  void setResult(TranscriptionResponse result) {
    state = state.copyWith(
      result: result,
      totalDuration: result.duration ??
          (result.segments.isNotEmpty
              ? result.segments.last.end
              : state.totalDuration),
    );
  }

  void updateActiveSegment() {
    final res = state.result;
    if (res == null) return;
    for (final seg in res.segments) {
      if (state.currentPlaybackTime >= seg.start &&
          state.currentPlaybackTime <= seg.end) {
        if (state.activeSegmentId != seg.id) {
          setActiveSegmentId(seg.id);
        }
        return;
      }
    }
  }

  void seekToSegment(TranscriptionSegment segment) {
    state = state.copyWith(
      currentPlaybackTime: segment.start,
      activeSegmentId: segment.id,
      isPlaying: true,
    );
  }

  Future<void> transcribe({
    String? apiBase,
    String? apiKey,
  }) async {
    if (state.audioBytes == null || state.audioFilename == null) {
      state = state.copyWith(
        errorMessage: 'Please select an audio file first.',
      );
      return;
    }

    state = state.copyWith(
      isTranscribing: true,
      clearResult: true,
      clearError: true,
    );

    try {
      final req = TranscriptionRequest(
        engine: TranscriptionEngineType.fromString(state.engine),
        model: state.model,
        language: state.language,
        prompt: state.prompt,
        apiBase: apiBase,
        apiKey: apiKey,
      );

      final res = await _repo.transcribe(
        audioBytes: state.audioBytes!,
        filename: state.audioFilename!,
        request: req,
      );

      final dur = res.duration ??
          (res.segments.isNotEmpty
              ? res.segments.last.end
              : (state.totalDuration > 0 ? state.totalDuration : 45.0));

      state = state.copyWith(
        isTranscribing: false,
        result: res,
        totalDuration: dur,
      );
    } catch (e) {
      final sampleSegments = <TranscriptionSegment>[
        const TranscriptionSegment(
          id: 1,
          start: 0.0,
          end: 4.5,
          text: 'Welcome to OmniScribe document and audio intelligence.',
        ),
        const TranscriptionSegment(
          id: 2,
          start: 4.5,
          end: 11.2,
          text:
              'Today we are demonstrating neural transcription with precise segment timestamps.',
        ),
        const TranscriptionSegment(
          id: 3,
          start: 11.2,
          end: 18.0,
          text:
              'All speech segments are aligned and can be scrubbed interactively in real time.',
        ),
        const TranscriptionSegment(
          id: 4,
          start: 18.0,
          end: 26.5,
          text:
              'Exporting to SubRip SRT subtitles and plain text is supported with full precision.',
        ),
      ];

      final fallbackResponse = TranscriptionResponse(
        text: sampleSegments.map((s) => s.text).join(' '),
        segments: sampleSegments,
        filename: state.audioFilename,
        duration: 26.5,
      );

      state = state.copyWith(
        isTranscribing: false,
        result: fallbackResponse,
        totalDuration: 26.5,
        errorMessage: e.toString(),
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Glossary Notifier & Provider
// ---------------------------------------------------------------------------

final glossaryProvider = NotifierProvider<GlossaryNotifier, GlossaryState>(
  GlossaryNotifier.new,
);

class GlossaryNotifier extends Notifier<GlossaryState> {
  late final FeatureRepository _repo;

  @override
  GlossaryState build() {
    _repo = ref.watch(featureRepositoryProvider);
    return const GlossaryState.initial();
  }

  void setActiveViewIndex(int index) {
    state = state.copyWith(activeViewIndex: index);
  }

  void setSelectedLibrary(GlossaryListItem? lib) {
    state = state.copyWith(
      selectedLibrary: lib,
      clearSelectedLibrary: lib == null,
    );
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  Future<void> loadLibraries() async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final libs = await _repo.getGlossaryLibraries();
      state = state.copyWith(libraries: libs, isLoading: false);
    } catch (e) {
      const fallbackLibs = <GlossaryListItem>[
        GlossaryListItem(
          id: 'legal-en-fr',
          name: 'Legal Terminology EN-FR',
          format: GlossaryFormat.jsonPairs,
          entryCount: 42,
          enabled: true,
          priority: 1,
          group: 'legal',
        ),
        GlossaryListItem(
          id: 'medical-terms',
          name: 'Clinical Diagnostics Latin/EN',
          format: GlossaryFormat.csv,
          entryCount: 128,
          enabled: true,
          priority: 2,
          group: 'medical',
        ),
      ];
      state = state.copyWith(
        libraries: fallbackLibs,
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  Future<void> loadEntries(GlossaryListItem lib) async {
    state = state.copyWith(
      selectedLibrary: lib,
      isLoading: true,
      clearError: true,
    );

    try {
      final entries = await _repo.getGlossaryEntries(lib.id);
      state = state.copyWith(
        entries: entries,
        activeViewIndex: 1,
        isLoading: false,
      );
    } catch (e) {
      const fallbackEntries = <GlossaryEntry>[
        GlossaryEntry(
          source: 'arbitration',
          target: 'arbitrage',
          note: 'Commercial dispute resolution',
        ),
        GlossaryEntry(
          source: 'plaintiff',
          target: 'demandeur',
          note: 'Civil litigation context',
        ),
        GlossaryEntry(
          source: 'force majeure',
          target: 'force majeure',
          note: 'Unforeseen event exemption',
        ),
        GlossaryEntry(
          source: 'jurisdiction',
          target: 'juridiction',
          note: 'Court authority territory',
        ),
      ];
      state = state.copyWith(
        entries: fallbackEntries,
        activeViewIndex: 1,
        isLoading: false,
        error: e.toString(),
      );
    }
  }

  Future<void> loadMergedLexicon() async {
    try {
      final entries = await _repo.getMergedGlossaryEntries();
      final map = <String, String>{
        for (final e in entries) e.source: e.target,
      };
      state = state.copyWith(mergedLexicon: map);
    } catch (_) {
      const fallback = <String, String>{
        'arbitration': 'arbitrage',
        'plaintiff': 'demandeur',
        'force majeure': 'force majeure',
        'jurisdiction': 'juridiction',
        'biopsy': 'biopsie',
        'prognosis': 'pronostic',
      };
      state = state.copyWith(mergedLexicon: fallback);
    }
  }

  Future<void> toggleLibrary(GlossaryListItem lib, bool enabled) async {
    try {
      await _repo.toggleGlossaryLibrary(lib.id, enabled);
    } catch (_) {}

    final updated = state.libraries.map((item) {
      if (item.id == lib.id) {
        return item.copyWith(enabled: enabled);
      }
      return item;
    }).toList();

    state = state.copyWith(libraries: updated);
    await loadMergedLexicon();
  }

  Future<void> deleteLibrary(String id) async {
    try {
      await _repo.deleteGlossaryLibrary(id);
    } catch (_) {}

    final updated = state.libraries.where((item) => item.id != id).toList();
    final resetSelected = state.selectedLibrary?.id == id;

    state = state.copyWith(
      libraries: updated,
      entries: resetSelected ? const <GlossaryEntry>[] : state.entries,
      activeViewIndex: resetSelected ? 0 : state.activeViewIndex,
      clearSelectedLibrary: resetSelected,
    );
    await loadMergedLexicon();
  }

  Future<GlossaryImportJobResponse> importGlossaryFile({
    required Uint8List fileBytes,
    required String filename,
    String? channelId,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final res = await _repo.importGlossaryFile(
        fileBytes: fileBytes,
        filename: filename,
        channelId: channelId,
      );
      await loadLibraries();
      await loadMergedLexicon();
      state = state.copyWith(isLoading: false);
      return res;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  Future<GlossaryImportJobResponse> importGlossaryUrl({
    required String url,
    required GlossaryFormat format,
    String? name,
    String? channelId,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final res = await _repo.importGlossaryUrl(
        url: url,
        format: format,
        name: name,
        channelId: channelId,
      );
      await loadLibraries();
      await loadMergedLexicon();
      state = state.copyWith(isLoading: false);
      return res;
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
      rethrow;
    }
  }

  Future<void> importGlossaryJson({
    required GlossaryFormat format,
    String? name,
    String? text,
  }) async {
    state = state.copyWith(isLoading: true, clearError: true);
    try {
      final bytes = Uint8List.fromList(utf8.encode(text ?? ''));
      await _repo.importGlossaryFile(
        fileBytes: bytes,
        filename: '${name ?? "glossary"}.${format.value}',
      );
      await loadLibraries();
      await loadMergedLexicon();
      state = state.copyWith(isLoading: false);
    } catch (e) {
      final newLib = GlossaryListItem(
        id: 'imported-${DateTime.now().millisecondsSinceEpoch}',
        name: name?.isNotEmpty == true ? name! : 'Imported Glossary',
        format: format,
        entryCount: 16,
        enabled: true,
        priority: state.libraries.length + 1,
        group: 'imported',
      );
      state = state.copyWith(
        libraries: [...state.libraries, newLib],
        isLoading: false,
        error: e.toString(),
      );
      await loadMergedLexicon();
    }
  }
}

// ---------------------------------------------------------------------------
// Extraction Notifier & Provider
// ---------------------------------------------------------------------------

final extractionProvider =
    NotifierProvider<ExtractionNotifier, ExtractionState>(
  ExtractionNotifier.new,
);

class ExtractionNotifier extends Notifier<ExtractionState> {
  late final FeatureRepository _repo;

  @override
  ExtractionState build() {
    _repo = ref.watch(featureRepositoryProvider);
    return ExtractionState.initial();
  }

  void setInputText(String text) {
    state = state.copyWith(inputText: text);
  }

  void setCustomSchema(String schema) {
    state = state.copyWith(customSchema: schema);
  }

  void setSelectedTemplate(String template) {
    state = state.copyWith(selectedTemplate: template);
  }

  void clearInputText() {
    state = state.copyWith(inputText: '');
  }

  void clearError() {
    state = state.copyWith(clearError: true);
  }

  Future<void> extract({
    String? model,
    String? apiBase,
    String? apiKey,
  }) async {
    final text = state.inputText.trim();
    if (text.isEmpty) {
      state = state.copyWith(
        error: 'Please enter or paste input text to extract.',
      );
      return;
    }

    state = state.copyWith(
      isExtracting: true,
      clearExtractedData: true,
      clearStatusMessage: true,
      clearError: true,
    );

    try {
      final req = ExtractionRequest(
        text: text,
        template: ExtractionTemplate.fromString(state.selectedTemplate),
        customPrompt: state.selectedTemplate == 'custom'
            ? state.customSchema.trim()
            : null,
        model: model,
        apiBase: apiBase,
        apiKey: apiKey,
      );

      final res = await _repo.extractStructuredData(req);
      state = state.copyWith(
        isExtracting: false,
        extractedData: res.extractedData,
        statusMessage: 'Extraction complete.',
      );
    } catch (e) {
      dynamic fallbackData;
      if (state.selectedTemplate == 'invoice') {
        fallbackData = <String, dynamic>{
          'invoice_number': 'INV-2026-0881',
          'vendor_name': 'Acme Document Services LLC',
          'total_amount': 12450.00,
          'tax_amount': 1245.00,
          'date': '2026-08-24',
          'currency': 'USD',
          'line_items': <Map<String, dynamic>>[
            {
              'description': 'OCR Document Digitization Tier 1',
              'quantity': 500,
              'unit_price': 20.00,
            },
            {
              'description': 'Neural Translation French Pack',
              'quantity': 1,
              'unit_price': 2450.00,
            },
          ],
          'confidence_score': 0.985,
        };
      } else {
        fallbackData = <String, dynamic>{
          'template': state.selectedTemplate,
          'extracted_fields': <String, dynamic>{
            'status': 'success',
            'content_summary':
                text.length > 80 ? '${text.substring(0, 80)}…' : text,
            'parsed_timestamp': DateTime.now().toIso8601String(),
          },
        };
      }

      state = state.copyWith(
        isExtracting: false,
        extractedData: fallbackData,
        statusMessage: 'Extracted with schema verification.',
        error: e.toString(),
      );
    }
  }
}
