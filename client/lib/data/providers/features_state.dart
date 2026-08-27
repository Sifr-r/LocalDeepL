import 'dart:convert';
import 'package:collection/collection.dart';
import 'package:flutter/foundation.dart';
import 'package:omniscribe_client/data/models/feature_models.dart';

/// Immutable state for the Translation feature vertical.
@immutable
class TranslationState {
  const TranslationState({
    this.sourceText = '',
    this.targetLanguage = 'French',
    this.selectedModel = '',
    this.useNllb = false,
    this.isTranslating = false,
    this.translatedOutput = '',
    this.error,
    this.asyncJobId,
    this.asyncStatus,
  });

  const TranslationState.initial()
      : sourceText = '',
        targetLanguage = 'French',
        selectedModel = '',
        useNllb = false,
        isTranslating = false,
        translatedOutput = '',
        error = null,
        asyncJobId = null,
        asyncStatus = null;

  final String sourceText;
  final String targetLanguage;
  final String selectedModel;
  final bool useNllb;
  final bool isTranslating;
  final String translatedOutput;
  final String? error;
  final String? asyncJobId;
  final String? asyncStatus;

  TranslationState copyWith({
    String? sourceText,
    String? targetLanguage,
    String? selectedModel,
    bool? useNllb,
    bool? isTranslating,
    String? translatedOutput,
    String? error,
    String? asyncJobId,
    String? asyncStatus,
    bool clearError = false,
    bool clearAsyncJobId = false,
    bool clearAsyncStatus = false,
  }) {
    return TranslationState(
      sourceText: sourceText ?? this.sourceText,
      targetLanguage: targetLanguage ?? this.targetLanguage,
      selectedModel: selectedModel ?? this.selectedModel,
      useNllb: useNllb ?? this.useNllb,
      isTranslating: isTranslating ?? this.isTranslating,
      translatedOutput: translatedOutput ?? this.translatedOutput,
      error: clearError ? null : (error ?? this.error),
      asyncJobId: clearAsyncJobId ? null : (asyncJobId ?? this.asyncJobId),
      asyncStatus: clearAsyncStatus ? null : (asyncStatus ?? this.asyncStatus),
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is TranslationState &&
        other.sourceText == sourceText &&
        other.targetLanguage == targetLanguage &&
        other.selectedModel == selectedModel &&
        other.useNllb == useNllb &&
        other.isTranslating == isTranslating &&
        other.translatedOutput == translatedOutput &&
        other.error == error &&
        other.asyncJobId == asyncJobId &&
        other.asyncStatus == asyncStatus;
  }

  @override
  int get hashCode => Object.hash(
        sourceText,
        targetLanguage,
        selectedModel,
        useNllb,
        isTranslating,
        translatedOutput,
        error,
        asyncJobId,
        asyncStatus,
      );
}

/// Immutable state for the Voice & Audio Transcription feature vertical.
@immutable
class TranscriptionState {
  const TranscriptionState({
    this.audioBytes,
    this.audioFilename,
    this.engine = 'api',
    this.model = 'whisper-1',
    this.language,
    this.prompt,
    this.isTranscribing = false,
    this.result,
    this.errorMessage,
    this.isPlaying = false,
    this.currentPlaybackTime = 0.0,
    this.totalDuration = 0.0,
    this.activeSegmentId,
  });

  const TranscriptionState.initial()
      : audioBytes = null,
        audioFilename = null,
        engine = 'api',
        model = 'whisper-1',
        language = null,
        prompt = null,
        isTranscribing = false,
        result = null,
        errorMessage = null,
        isPlaying = false,
        currentPlaybackTime = 0.0,
        totalDuration = 0.0,
        activeSegmentId = null;

  final Uint8List? audioBytes;
  final String? audioFilename;
  final String engine;
  final String model;
  final String? language;
  final String? prompt;
  final bool isTranscribing;
  final TranscriptionResponse? result;
  final String? errorMessage;
  final bool isPlaying;
  final double currentPlaybackTime;
  final double totalDuration;
  final int? activeSegmentId;

  String? get error => errorMessage;

  TranscriptionState copyWith({
    Uint8List? audioBytes,
    String? audioFilename,
    String? engine,
    String? model,
    String? language,
    String? prompt,
    bool? isTranscribing,
    TranscriptionResponse? result,
    String? errorMessage,
    bool? isPlaying,
    double? currentPlaybackTime,
    double? totalDuration,
    int? activeSegmentId,
    bool clearAudio = false,
    bool clearResult = false,
    bool clearError = false,
    bool clearActiveSegment = false,
    bool clearLanguage = false,
    bool clearPrompt = false,
  }) {
    return TranscriptionState(
      audioBytes: clearAudio ? null : (audioBytes ?? this.audioBytes),
      audioFilename: clearAudio ? null : (audioFilename ?? this.audioFilename),
      engine: engine ?? this.engine,
      model: model ?? this.model,
      language: clearLanguage ? null : (language ?? this.language),
      prompt: clearPrompt ? null : (prompt ?? this.prompt),
      isTranscribing: isTranscribing ?? this.isTranscribing,
      result: clearResult ? null : (result ?? this.result),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
      isPlaying: isPlaying ?? this.isPlaying,
      currentPlaybackTime: currentPlaybackTime ?? this.currentPlaybackTime,
      totalDuration: totalDuration ?? this.totalDuration,
      activeSegmentId:
          clearActiveSegment ? null : (activeSegmentId ?? this.activeSegmentId),
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is TranscriptionState &&
        listEquals(other.audioBytes, audioBytes) &&
        other.audioFilename == audioFilename &&
        other.engine == engine &&
        other.model == model &&
        other.language == language &&
        other.prompt == prompt &&
        other.isTranscribing == isTranscribing &&
        other.result == result &&
        other.errorMessage == errorMessage &&
        other.isPlaying == isPlaying &&
        other.currentPlaybackTime == currentPlaybackTime &&
        other.totalDuration == totalDuration &&
        other.activeSegmentId == activeSegmentId;
  }

  @override
  int get hashCode => Object.hash(
        audioBytes != null ? Object.hashAll(audioBytes!) : null,
        audioFilename,
        engine,
        model,
        language,
        prompt,
        isTranscribing,
        result,
        errorMessage,
        isPlaying,
        currentPlaybackTime,
        totalDuration,
        activeSegmentId,
      );
}

/// Immutable state for the Terminology Glossary feature vertical.
@immutable
class GlossaryState {
  const GlossaryState({
    this.libraries = const <GlossaryListItem>[],
    this.selectedLibrary,
    this.entries = const <GlossaryEntry>[],
    this.mergedLexicon = const <String, String>{},
    this.activeViewIndex = 0,
    this.isLoading = false,
    this.error,
  });

  const GlossaryState.initial()
      : libraries = const <GlossaryListItem>[],
        selectedLibrary = null,
        entries = const <GlossaryEntry>[],
        mergedLexicon = const <String, String>{},
        activeViewIndex = 0,
        isLoading = false,
        error = null;

  final List<GlossaryListItem> libraries;
  final GlossaryListItem? selectedLibrary;
  final List<GlossaryEntry> entries;
  final Map<String, String> mergedLexicon;
  final int activeViewIndex;
  final bool isLoading;
  final String? error;

  GlossaryState copyWith({
    List<GlossaryListItem>? libraries,
    GlossaryListItem? selectedLibrary,
    List<GlossaryEntry>? entries,
    Map<String, String>? mergedLexicon,
    int? activeViewIndex,
    bool? isLoading,
    String? error,
    bool clearSelectedLibrary = false,
    bool clearError = false,
  }) {
    return GlossaryState(
      libraries: libraries ?? this.libraries,
      selectedLibrary: clearSelectedLibrary
          ? null
          : (selectedLibrary ?? this.selectedLibrary),
      entries: entries ?? this.entries,
      mergedLexicon: mergedLexicon ?? this.mergedLexicon,
      activeViewIndex: activeViewIndex ?? this.activeViewIndex,
      isLoading: isLoading ?? this.isLoading,
      error: clearError ? null : (error ?? this.error),
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is GlossaryState &&
        listEquals(other.libraries, libraries) &&
        other.selectedLibrary == selectedLibrary &&
        listEquals(other.entries, entries) &&
        mapEquals(other.mergedLexicon, mergedLexicon) &&
        other.activeViewIndex == activeViewIndex &&
        other.isLoading == isLoading &&
        other.error == error;
  }

  @override
  int get hashCode => Object.hash(
        Object.hashAll(libraries),
        selectedLibrary,
        Object.hashAll(entries),
        Object.hashAll(mergedLexicon.entries),
        activeViewIndex,
        isLoading,
        error,
      );
}

/// Immutable state for the Structured Information Extraction feature vertical.
@immutable
class ExtractionState {
  ExtractionState({
    this.inputText = '',
    String? customSchema,
    this.selectedTemplate = 'invoice',
    this.isExtracting = false,
    this.extractedData,
    this.statusMessage,
    this.error,
  }) : customSchema = customSchema ?? defaultCustomSchema;

  ExtractionState.initial()
      : inputText = '',
        customSchema = defaultCustomSchema,
        selectedTemplate = 'invoice',
        isExtracting = false,
        extractedData = null,
        statusMessage = null,
        error = null;

  static final String defaultCustomSchema =
      const JsonEncoder.withIndent('  ').convert(<String, dynamic>{
    'invoice_number': 'string',
    'vendor_name': 'string',
    'total_amount': 'number',
    'tax_amount': 'number',
    'date': 'string',
    'line_items': <Map<String, dynamic>>[
      {
        'description': 'string',
        'quantity': 'number',
        'unit_price': 'number',
      }
    ],
  });

  final String inputText;
  final String customSchema;
  final String selectedTemplate;
  final bool isExtracting;
  final dynamic extractedData;
  final String? statusMessage;
  final String? error;

  ExtractionState copyWith({
    String? inputText,
    String? customSchema,
    String? selectedTemplate,
    bool? isExtracting,
    dynamic extractedData,
    String? statusMessage,
    String? error,
    bool clearExtractedData = false,
    bool clearStatusMessage = false,
    bool clearError = false,
  }) {
    return ExtractionState(
      inputText: inputText ?? this.inputText,
      customSchema: customSchema ?? this.customSchema,
      selectedTemplate: selectedTemplate ?? this.selectedTemplate,
      isExtracting: isExtracting ?? this.isExtracting,
      extractedData:
          clearExtractedData ? null : (extractedData ?? this.extractedData),
      statusMessage:
          clearStatusMessage ? null : (statusMessage ?? this.statusMessage),
      error: clearError ? null : (error ?? this.error),
    );
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is ExtractionState &&
        other.inputText == inputText &&
        other.customSchema == customSchema &&
        other.selectedTemplate == selectedTemplate &&
        other.isExtracting == isExtracting &&
        _deepEquals(other.extractedData, extractedData) &&
        other.statusMessage == statusMessage &&
        other.error == error;
  }

  static bool _deepEquals(dynamic a, dynamic b) {
    if (a == null && b == null) return true;
    if (a == null || b == null) return false;
    if (a is Map && b is Map) {
      if (a.length != b.length) return false;
      for (final key in a.keys) {
        if (!b.containsKey(key) || !_deepEquals(a[key], b[key])) return false;
      }
      return true;
    }
    if (a is List && b is List) {
      if (a.length != b.length) return false;
      for (int i = 0; i < a.length; i++) {
        if (!_deepEquals(a[i], b[i])) return false;
      }
      return true;
    }
    return a == b;
  }

  @override
  int get hashCode => Object.hash(
        inputText,
        customSchema,
        selectedTemplate,
        isExtracting,
        // _deepEquals walks Maps/Lists, so the hash must agree with that
        // contract; using Object.hash on a dynamic Map/List would yield an
        // identity-based hash and silently break Set/Map<ExtractionState, T>.
        const DeepCollectionEquality().hash(extractedData),
        statusMessage,
        error,
      );
}
