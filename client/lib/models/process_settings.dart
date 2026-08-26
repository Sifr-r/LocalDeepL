import 'package:flutter/foundation.dart';

/// Available OCR pipeline modes
enum PipelineMode {
  hybrid('hybrid', 'Hybrid (OCR + VLM)'),
  grounded('grounded', 'Grounded BBox'),
  groundedNative('grounded_native', 'Grounded Native');

  const PipelineMode(this.value, this.label);
  final String value;
  final String label;

  static PipelineMode fromValue(String? value) {
    return PipelineMode.values.firstWhere(
      (e) => e.value == value,
      orElse: () => PipelineMode.hybrid,
    );
  }
}

/// Dense document layout mode
enum DenseMode {
  auto('auto', 'Auto'),
  on('on', 'On'),
  off('off', 'Off');

  const DenseMode(this.value, this.label);
  final String value;
  final String label;

  static DenseMode fromValue(String? value) {
    return DenseMode.values.firstWhere(
      (e) => e.value == value,
      orElse: () => DenseMode.auto,
    );
  }
}

/// Spellchecking languages
enum SpellcheckMode {
  none('none', 'None'),
  enUS('en-US', 'English (US)'),
  ar('ar', 'Arabic'),
  de('de', 'German'),
  es('es', 'Spanish'),
  fr('fr', 'French');

  const SpellcheckMode(this.value, this.label);
  final String value;
  final String label;

  static SpellcheckMode fromValue(String? value) {
    return SpellcheckMode.values.firstWhere(
      (e) => e.value == value,
      orElse: () => SpellcheckMode.none,
    );
  }
}

/// Document Processor descriptor
class DocumentProcessorInfo {
  final String id;
  final String label;
  final String description;

  const DocumentProcessorInfo({
    required this.id,
    required this.label,
    required this.description,
  });

  static const List<DocumentProcessorInfo> all = [
    DocumentProcessorInfo(
      id: 'reading_order',
      label: 'Reading Order',
      description:
          'Determines the natural human reading sequence across multiple columns and blocks.',
    ),
    DocumentProcessorInfo(
      id: 'quality_analysis',
      label: 'Quality Analysis',
      description:
          'Scores block clarity, contrast, and OCR character-level confidence.',
    ),
    DocumentProcessorInfo(
      id: 'structure_analysis',
      label: 'Structure Analysis',
      description:
          'Detects hierarchical document structure: headers, footers, body, lists.',
    ),
    DocumentProcessorInfo(
      id: 'section_analysis',
      label: 'Section Analysis',
      description:
          'Segments text into coherent semantic sections and chapter boundaries.',
    ),
    DocumentProcessorInfo(
      id: 'layout_enrichment',
      label: 'Layout Enrichment',
      description:
          'Enriches bounding boxes with semantic typography and alignment metadata.',
    ),
    DocumentProcessorInfo(
      id: 'table_extraction',
      label: 'Table Extraction',
      description:
          'Extracts structured table grids and cell relations into clean Markdown/JSON.',
    ),
  ];
}

/// Complete OCR processing configuration settings matching ProcessSettings in api.ts
@immutable
class ProcessSettings {
  const ProcessSettings({
    this.apiBase = 'http://localhost:8000/v1',
    this.apiKey = '',
    this.model = 'gpt-4o',
    this.pipelineMode = PipelineMode.hybrid,
    this.dpi = 300,
    this.concurrency = 4,
    this.denseMode = DenseMode.auto,
    this.denseThreshold = 0.7,
    this.pages,
    this.refine = true,
    this.maxImageDim = 2048,
    this.selfCorrection = true,
    this.binarize = false,
    this.dualEngine = false,
    this.spellcheck = SpellcheckMode.none,
    this.crossPage = false,
    this.preprocessPages = true,
    this.orientationDetection = true,
    this.deskew = true,
    this.denoise = false,
    this.normalizeContrast = true,
    this.cropCleanup = false,
    this.qualityRouting = false,
    this.qualityRepairEnabled = true,
    this.qualityTarget = 0.85,
    this.maxRetries = 3,
    this.documentProcessors = const [
      'reading_order',
      'quality_analysis',
      'structure_analysis',
    ],
    this.useAsync = true,
  });

  final String apiBase;
  final String apiKey;
  final String model;
  final PipelineMode pipelineMode;
  final int dpi;
  final int concurrency;
  final DenseMode denseMode;
  final double denseThreshold;
  final String? pages;
  final bool refine;
  final int maxImageDim;
  final bool selfCorrection;
  final bool binarize;
  final bool dualEngine;
  final SpellcheckMode spellcheck;
  final bool crossPage;
  final bool preprocessPages;
  final bool orientationDetection;
  final bool deskew;
  final bool denoise;
  final bool normalizeContrast;
  final bool cropCleanup;
  final bool qualityRouting;
  final bool qualityRepairEnabled;
  final double qualityTarget;
  final int maxRetries;
  final List<String> documentProcessors;
  final bool useAsync;

  factory ProcessSettings.fromJson(Map<String, dynamic> json) {
    return ProcessSettings(
      apiBase: json['api_base'] as String? ?? 'http://localhost:8000/v1',
      apiKey: json['api_key'] as String? ?? '',
      model: json['model'] as String? ?? 'gpt-4o',
      pipelineMode: PipelineMode.fromValue(json['pipeline_mode'] as String?),
      dpi: (json['dpi'] as num?)?.toInt() ?? 300,
      concurrency: (json['concurrency'] as num?)?.toInt() ?? 4,
      denseMode: DenseMode.fromValue(json['dense_mode'] as String?),
      denseThreshold: (json['dense_threshold'] as num?)?.toDouble() ?? 0.7,
      pages: json['pages'] as String?,
      refine: json['refine'] as bool? ?? true,
      maxImageDim: (json['max_image_dim'] as num?)?.toInt() ?? 2048,
      selfCorrection: json['self_correction'] as bool? ?? true,
      binarize: json['binarize'] as bool? ?? false,
      dualEngine: json['dual_engine'] as bool? ?? false,
      spellcheck: SpellcheckMode.fromValue(json['spellcheck'] as String?),
      crossPage: json['cross_page'] as bool? ?? false,
      preprocessPages: json['preprocess_pages'] as bool? ?? true,
      orientationDetection: json['orientation_detection'] as bool? ?? true,
      deskew: json['deskew'] as bool? ?? true,
      denoise: json['denoise'] as bool? ?? false,
      normalizeContrast: json['normalize_contrast'] as bool? ?? true,
      cropCleanup: json['crop_cleanup'] as bool? ?? false,
      qualityRouting: json['quality_routing'] as bool? ?? false,
      qualityRepairEnabled: json['quality_repair_enabled'] as bool? ?? true,
      qualityTarget: (json['quality_target'] as num?)?.toDouble() ?? 0.85,
      maxRetries: (json['max_retries'] as num?)?.toInt() ?? 3,
      documentProcessors: (json['document_processors'] as List<dynamic>?)
              ?.map((e) => e.toString())
              .toList() ??
          const ['reading_order', 'quality_analysis', 'structure_analysis'],
      useAsync: json['use_async'] as bool? ?? true,
    );
  }

  Map<String, dynamic> toJson() => {
        'api_base': apiBase,
        'api_key': apiKey,
        'model': model,
        'pipeline_mode': pipelineMode.value,
        'dpi': dpi,
        'concurrency': concurrency,
        'dense_mode': denseMode.value,
        'dense_threshold': denseThreshold,
        if (pages != null) 'pages': pages,
        'refine': refine,
        'max_image_dim': maxImageDim,
        'self_correction': selfCorrection,
        'binarize': binarize,
        'dual_engine': dualEngine,
        'spellcheck': spellcheck.value,
        'cross_page': crossPage,
        'preprocess_pages': preprocessPages,
        'orientation_detection': orientationDetection,
        'deskew': deskew,
        'denoise': denoise,
        'normalize_contrast': normalizeContrast,
        'crop_cleanup': cropCleanup,
        'quality_routing': qualityRouting,
        'quality_repair_enabled': qualityRepairEnabled,
        'quality_target': qualityTarget,
        'max_retries': maxRetries,
        'document_processors': documentProcessors,
        'use_async': useAsync,
      };

  ProcessSettings copyWith({
    String? apiBase,
    String? apiKey,
    String? model,
    PipelineMode? pipelineMode,
    int? dpi,
    int? concurrency,
    DenseMode? denseMode,
    double? denseThreshold,
    String? pages,
    bool? refine,
    int? maxImageDim,
    bool? selfCorrection,
    bool? binarize,
    bool? dualEngine,
    SpellcheckMode? spellcheck,
    bool? crossPage,
    bool? preprocessPages,
    bool? orientationDetection,
    bool? deskew,
    bool? denoise,
    bool? normalizeContrast,
    bool? cropCleanup,
    bool? qualityRouting,
    bool? qualityRepairEnabled,
    double? qualityTarget,
    int? maxRetries,
    List<String>? documentProcessors,
    bool? useAsync,
  }) {
    return ProcessSettings(
      apiBase: apiBase ?? this.apiBase,
      apiKey: apiKey ?? this.apiKey,
      model: model ?? this.model,
      pipelineMode: pipelineMode ?? this.pipelineMode,
      dpi: dpi ?? this.dpi,
      concurrency: concurrency ?? this.concurrency,
      denseMode: denseMode ?? this.denseMode,
      denseThreshold: denseThreshold ?? this.denseThreshold,
      pages: pages ?? this.pages,
      refine: refine ?? this.refine,
      maxImageDim: maxImageDim ?? this.maxImageDim,
      selfCorrection: selfCorrection ?? this.selfCorrection,
      binarize: binarize ?? this.binarize,
      dualEngine: dualEngine ?? this.dualEngine,
      spellcheck: spellcheck ?? this.spellcheck,
      crossPage: crossPage ?? this.crossPage,
      preprocessPages: preprocessPages ?? this.preprocessPages,
      orientationDetection: orientationDetection ?? this.orientationDetection,
      deskew: deskew ?? this.deskew,
      denoise: denoise ?? this.denoise,
      normalizeContrast: normalizeContrast ?? this.normalizeContrast,
      cropCleanup: cropCleanup ?? this.cropCleanup,
      qualityRouting: qualityRouting ?? this.qualityRouting,
      qualityRepairEnabled: qualityRepairEnabled ?? this.qualityRepairEnabled,
      qualityTarget: qualityTarget ?? this.qualityTarget,
      maxRetries: maxRetries ?? this.maxRetries,
      documentProcessors: documentProcessors ?? this.documentProcessors,
      useAsync: useAsync ?? this.useAsync,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is ProcessSettings &&
          runtimeType == other.runtimeType &&
          apiBase == other.apiBase &&
          apiKey == other.apiKey &&
          model == other.model &&
          pipelineMode == other.pipelineMode &&
          dpi == other.dpi &&
          concurrency == other.concurrency &&
          denseMode == other.denseMode &&
          denseThreshold == other.denseThreshold &&
          pages == other.pages &&
          refine == other.refine &&
          maxImageDim == other.maxImageDim &&
          selfCorrection == other.selfCorrection &&
          binarize == other.binarize &&
          dualEngine == other.dualEngine &&
          spellcheck == other.spellcheck &&
          crossPage == other.crossPage &&
          preprocessPages == other.preprocessPages &&
          orientationDetection == other.orientationDetection &&
          deskew == other.deskew &&
          denoise == other.denoise &&
          normalizeContrast == other.normalizeContrast &&
          cropCleanup == other.cropCleanup &&
          qualityRouting == other.qualityRouting &&
          qualityRepairEnabled == other.qualityRepairEnabled &&
          qualityTarget == other.qualityTarget &&
          maxRetries == other.maxRetries &&
          listEquals(documentProcessors, other.documentProcessors) &&
          useAsync == other.useAsync;

  @override
  int get hashCode => Object.hashAll([
        apiBase,
        apiKey,
        model,
        pipelineMode,
        dpi,
        concurrency,
        denseMode,
        denseThreshold,
        pages,
        refine,
        maxImageDim,
        selfCorrection,
        binarize,
        dualEngine,
        spellcheck,
        crossPage,
        preprocessPages,
        orientationDetection,
        deskew,
        denoise,
        normalizeContrast,
        cropCleanup,
        qualityRouting,
        qualityRepairEnabled,
        qualityTarget,
        maxRetries,
        Object.hashAll(documentProcessors),
        useAsync,
      ]);
}
