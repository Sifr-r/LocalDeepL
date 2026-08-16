/**
 * TypeScript API type definitions for OmniScribe Frontend
 * Matching Pydantic schemas in omniscribe.api.schemas
 */

export type PipelineMode = 'hybrid' | 'grounded' | 'grounded_native';
export type DenseMode = 'auto' | 'on' | 'off';
// Mirrors omniscribe.core.document.SpellcheckMode (dictionary languages).
export type SpellcheckMode = 'none' | 'ar' | 'en-US' | 'de' | 'es' | 'fr';

// Mirrors omniscribe.api.schemas.requests.DocumentProcessorName.
export type DocumentProcessorName =
  | 'reading_order'
  | 'quality_analysis'
  | 'structure_analysis'
  | 'section_analysis'
  | 'layout_enrichment'
  | 'table_extraction';

export type ExtractionTemplate = 'invoice' | 'resume' | 'academic' | 'custom';
export type DocumentExportFormat = 'json' | 'markdown' | 'text' | 'docling' | 'mineru';

export type GlossaryFormat =
  | 'csv'
  | 'tsv'
  | 'xliff'
  | 'tbx'
  | 'tmx'
  | 'git_glossary'
  | 'sql_table'
  | 'json_pairs';

export type TranscriptionEngineType = 'api' | 'whisper_api' | 'local' | 'whisper_local' | 'auto';

export interface ConfigUpdate {
  api_base?: string | null;
  api_key?: string | null;
  model?: string | null;
  concurrency?: number | null;
  dpi?: number | null;
  dense_mode?: DenseMode | null;
  dense_threshold?: number | null;
  max_image_dim?: number | null;
  refine?: boolean | null;
  verify_model?: boolean | null;
  pipeline_mode?: PipelineMode | null;
  self_correction?: boolean | null;
  binarize?: boolean | null;
  dual_engine?: boolean | null;
  spellcheck?: SpellcheckMode | null;
  cross_page?: boolean | null;
  preprocess_pages?: boolean | null;
  orientation_detection?: boolean | null;
  deskew?: boolean | null;
  denoise?: boolean | null;
  normalize_contrast?: boolean | null;
  crop_cleanup?: boolean | null;
  quality_routing?: boolean | null;
  handwriting_hint?: boolean | null;
  confidence_threshold?: number | null;
  document_processors?: DocumentProcessorName[] | null;
}

export interface ProcessSettings {
  api_base: string;
  api_key: string;
  model: string;
  pipeline_mode: PipelineMode;
  dpi: number;
  concurrency: number;
  dense_mode: DenseMode;
  dense_threshold: number;
  pages?: string | null;
  refine: boolean;
  max_image_dim: number;
  self_correction: boolean;
  binarize: boolean;
  dual_engine: boolean;
  spellcheck: SpellcheckMode;
  cross_page: boolean;
  preprocess_pages: boolean;
  orientation_detection: boolean;
  deskew: boolean;
  denoise: boolean;
  normalize_contrast: boolean;
  crop_cleanup: boolean;
  quality_routing: boolean;
  handwriting_hint?: boolean;
  confidence_threshold?: number;
  document_processors?: DocumentProcessorName[];
  chunk_pages?: number | null;
}

export interface TranslationRequest {
  text?: string;
  text_artifact_id?: string;
  text_artifact_token?: string;
  prompt_template?: string;
  target_language?: string;
  api_base?: string | null;
  api_key?: string | null;
  model?: string | null;
  glossary?: Record<string, unknown>[] | null;
  glossary_text?: string | null;
  sliding_window_words?: number;
  dual_translate?: boolean;
  second_api_base?: string | null;
  second_api_key?: string | null;
  second_model?: string | null;
}

export interface GlossaryRequest {
  entries?: Record<string, unknown>[] | null;
  text?: string | null;
}

export interface TreeTranslationRequest {
  text_artifact_id: string;
  text_artifact_token: string;
  prompt_template?: string;
  target_language?: string;
  api_base?: string | null;
  api_key?: string | null;
  model?: string | null;
  glossary?: Record<string, unknown>[] | null;
  dual_translate?: boolean;
  channel_id?: string | null;
}

export interface ExportHtmlRequest {
  text_artifact_id: string;
  text_artifact_token: string;
}

export interface ExportBlockTreeRequest {
  text_artifact_id: string;
  text_artifact_token: string;
  metadata_artifact_id?: string | null;
  metadata_artifact_token?: string | null;
}

export interface ExtractionRequest {
  text?: string;
  template?: ExtractionTemplate;
  custom_prompt?: string;
  api_base?: string | null;
  api_key?: string | null;
  model?: string | null;
}

export interface ExportDocxRequest {
  text?: string;
}

export interface DocumentExportRequest {
  text_artifact_id: string;
  text_artifact_token: string;
  export_format?: DocumentExportFormat;
  metadata_artifact_id?: string | null;
  metadata_artifact_token?: string | null;
}

export interface GlossaryImportSource {
  format: GlossaryFormat;
  text?: string | null;
  inline_bytes_b64?: string | null;
  url?: string | null;
  git_url?: string | null;
  git_ref?: string | null;
  git_path?: string | null;
  git_credentials?: string | null;
  sql_dsn?: string | null;
  sql_source_table?: string | null;
  sql_target_table?: string | null;
  sql_source_col?: string | null;
  sql_target_col?: string | null;
  sql_where?: string | null;
  encoding?: string | null;
  max_entries?: number | null;
  name?: string | null;
}

export interface GlossaryImportRequest {
  source: GlossaryImportSource;
  channel_id?: string | null;
  session_token?: string | null;
}

export interface GlossaryListItem {
  id: string;
  name: string;
  format: GlossaryFormat;
  source_uri?: string | null;
  encoding?: string | null;
  entry_count: number;
  enabled: boolean;
  priority: number;
  group: string;
}

export interface GlossaryEntry {
  source: string;
  target: string;
  note?: string;
  [key: string]: unknown;
}

export interface GlossaryToggleRequest {
  enabled: boolean;
}

export interface GlossaryReorderRequest {
  ordered_ids: string[];
}

export interface OcrConfigUpdate {
  ocr_api_base?: string | null;
  ocr_api_key?: string | null;
  ocr_model?: string | null;
  ocr_provider?: string | null;
}

export interface TranslationConfigUpdate {
  translation_api_base?: string | null;
  translation_api_key?: string | null;
  translation_model?: string | null;
  translation_provider?: string | null;
  sliding_window_words?: number | null;
  dual_translate?: boolean | null;
}

export interface AuthTokenUpdate {
  auth_token?: string | null;
}

export interface TranscriptionConfigUpdate {
  api_base?: string | null;
  api_key?: string | null;
  transcription_api_key?: string | null;
  model?: string | null;
  engine?: TranscriptionEngineType | null;
  language?: string | null;
  prompt?: string | null;
  temperature?: number | null;
}

export interface TranscriptionRequest {
  model?: string | null;
  engine?: TranscriptionEngineType | null;
  api_base?: string | null;
  api_key?: string | null;
  language?: string | null;
  prompt?: string | null;
  temperature?: number;
  translate_to?: string | null;
  channel_id?: string | null;
}

// Responses
export interface ProcessResponse {
  job_id: string;
  status: string;
}

export interface OCRStatusResponse {
  job_id: string;
  filename: string;
  status: string;
  created_at: number;
  started_at?: number | null;
  completed_at?: number | null;
  duration_s?: number | null;
  error?: string | null;
  text_artifact_id?: string | null;
  text_artifact_token?: string | null;
  text_artifact_url?: string | null;
  failed_pages?: number[] | null;
}

export interface JobRecordResponse {
  id: string;
  filename: string;
  model: string;
  pipeline_mode: string;
  pages?: string | null;
  duration_s: number;
  timestamp: string;
  status: string;
  failed_pages?: number[] | null;
}

export interface ClearJobsResponse {
  status: string;
}

export interface ConfigResponse {
  api_base: string;
  api_key: string;
  model: string;
  concurrency: number;
  dpi: number;
  dense_mode: string;
  dense_threshold: number;
  max_image_dim: number;
  refine: boolean;
  verify_model: boolean;
  pipeline_mode: string;
  self_correction: boolean;
  binarize: boolean;
  dual_engine: boolean;
  spellcheck: string;
  cross_page: boolean;
  preprocess_pages: boolean;
  orientation_detection: boolean;
  deskew: boolean;
  denoise: boolean;
  normalize_contrast: boolean;
  crop_cleanup: boolean;
  quality_routing: boolean;
  document_processors: string[];
  /**
   * UI-only flag: when true, the workstation submits to
   * ``POST /api/process/async`` and polls for the result PDF,
   * instead of the synchronous ``POST /api/process`` flow that
   * blocks the response until OCR finishes. Persisted in
   * ``configStore`` (local) but not in the server config — it's
   * a deployment preference, not a runtime knob.
   */
  use_async?: boolean;
  ocr_model?: string;
  ocr_api_base?: string;
  ocr_api_key?: string;
  translation_model?: string;
  translation_api_base?: string;
  translation_api_key?: string;
  sliding_window_words?: number;
  dual_translate?: boolean;
  transcription_model?: string;
  transcription_api_base?: string;
  transcription_api_key?: string;
  transcription_engine?: string;
  transcription_language?: string;
  transcription_prompt?: string;
  transcription_temperature?: number;
  max_upload_bytes?: number;
  security?: {
    max_upload_bytes: number;
    max_upload_mb: number;
  };
}

export interface OCRConfigResponse {
  ocr_api_base: string;
  ocr_api_key: string;
  ocr_model: string;
  ocr_provider?: string | null;
  ocr_auth_token?: string | null;
  concurrency: number;
  dpi: number;
  dense_mode: string;
  dense_threshold: number;
  max_image_dim: number;
  refine: boolean;
  verify_model: boolean;
  pipeline_mode: string;
  self_correction: boolean;
  binarize: boolean;
  dual_engine: boolean;
  spellcheck: string;
  cross_page: boolean;
  preprocess_pages: boolean;
  orientation_detection: boolean;
  deskew: boolean;
  denoise: boolean;
  normalize_contrast: boolean;
  crop_cleanup: boolean;
  quality_routing: boolean;
  document_processors: string[];
}

export interface TranslationConfigResponse {
  translation_api_base: string;
  translation_api_key: string;
  translation_model: string;
  translation_provider?: string | null;
  translation_auth_token?: string | null;
  sliding_window_words: number;
  dual_translate: boolean;
}

export interface NamespacedModelsResponse {
  models: string[];
  ocr: string[];
  translation: string[];
  ocr_error?: string | null;
  translation_error?: string | null;
}

export interface ModelsResponse {
  models: string[];
  error?: string | null;
}

export interface ExtractionResponse {
  extracted_data: unknown;
}

export interface TranslationResponse {
  translated_text: string;
}

export interface AsyncTranslationResponse {
  job_id: string;
  status: string;
}

export interface TranslationJobStatusResponse {
  job_id: string;
  state: string;
  status?: string | null;
  info?: unknown;
  result?: unknown;
  error?: string | null;
}

export interface GlossaryResponse {
  entries: unknown;
}

export interface TreeTranslationResponse {
  status: string;
  tree?: Record<string, unknown> | null;
  page_count?: number | null;
  block_count?: number | null;
  translated_pages?: Record<string, unknown> | null;
}

export interface NLLBTranslationResponse {
  translated_text: string;
  source_lang: string;
  target_lang: string;
}

export interface TranscriptionConfigResponse {
  transcription_api_base: string;
  transcription_api_key: string;
  transcription_model: string;
  transcription_engine: string;
  transcription_auth_token?: string | null;
  language?: string | null;
  prompt?: string | null;
  temperature: number;
}

export interface TranscriptionSegment {
  id?: number | null;
  start: number;
  end: number;
  text: string;
  [key: string]: unknown;
}

export interface TranscriptionJobResponse {
  text: string;
  filename?: string | null;
  language?: string | null;
  duration?: number | null;
  text_artifact_id?: string | null;
  text_artifact_token?: string | null;
  metadata_artifact_id?: string | null;
  metadata_artifact_token?: string | null;
  job_id?: string | null;
  segments: TranscriptionSegment[];
}

export interface GlossaryPreviewResponse {
  count: number;
  conflicts: Record<string, unknown>[];
  enabled_glossaries: string[];
}

export interface GlossaryImportJobResponse {
  glossary_id?: string | null;
  job_id?: string | null;
  format: GlossaryFormat;
  name: string;
  entry_count: number;
  warnings: string[];
  queued: boolean;
}

export interface ProviderPreset {
  id: string;
  name: string;
  category: string;
  description: string;
  recommended_base_url: string;
  api_base?: string;
  default_model: string;
  requires_key: boolean;
  notes: string;
}

export type LLMProvider = ProviderPreset;

export interface TextArtifactHandle {
  id: string;
  token: string;
  pageCount?: number;
}

export type RuntimeConfig = ConfigResponse;
export type JobRecord = JobRecordResponse;

/**
 * Per-job status returned by ``GET /api/process/status/{job_id}``.
 * Mirrors the fields exposed by :class:`OCRJobRecord.to_dict` on the
 * server. The status string union is the same as
 * :class:`OCRJobStatus` (StrEnum) on the server.
 */
export interface OcrJobStatusResponse {
  job_id: string;
  filename: string;
  status: 'pending' | 'processing' | 'complete' | 'error';
  created_at: number;
  started_at?: number | null;
  completed_at?: number | null;
  duration_s?: number | null;
  error?: string;
  text_artifact_id?: string;
  text_artifact_token?: string;
  text_artifact_url?: string;
  failed_pages?: number[];
}

// WebSocket frames — mirror the frame builders in
// omniscribe/api/services/progress.py (ProgressService.build_*_frame).
// The legacy progress frame intentionally has NO `type` discriminator:
// the server routes on shape ({status, percent, stage}) for backward
// compatibility. Every other frame carries a `type` field.
export interface ProgressFrame {
  type?: undefined;
  status: string;
  percent: number;
  stage: string;
  warning?: boolean;
}

export interface BlockCompleteFrame {
  type: 'block_complete';
  page_idx: number;
  block_idx: number;
  bbox: number[];
  text: string;
  kind: string;
  confidence: number | null;
}

export interface BlockRetryFrame {
  type: 'block_retry';
  page_idx: number;
  block_idx: number;
  attempt: number;
  confidence: number;
  target: number;
}

export interface BlockRevisedFrame {
  type: 'block_revised';
  page_idx: number;
  block_idx: number;
  attempt: number;
  bbox: number[];
  text: string;
  kind: string;
  confidence: number | null;
}

export interface PageCompleteFrame {
  type: 'page_complete';
  page_idx: number;
}

export interface QualitySummaryFrame {
  type: 'quality_summary';
  scope: string;
  target: number;
  avg_confidence: number;
  repaired_count: number;
  below_target_count: number;
  page_idx?: number;
}

export interface ChunkInitFrame {
  type: 'chunk_init';
  total_chunks: number;
  chapters: Record<string, unknown>[];
}

export interface ChunkCompleteFrame {
  type: 'chunk_complete';
  chunk_idx: number;
  total_chunks: number;
  page_range: string;
  source_pages: number[];
  text_chars_so_far: number;
  overall_percent?: number;
  chapters: Record<string, unknown>[];
}

export interface TranslateChunkCompleteFrame {
  type: 'translate_chunk_complete';
  chunk_idx: number;
  source_chars: number;
  translated_text: string;
  target_language: string;
}

export interface CancelledFrame {
  type: 'cancelled';
  status: string;
  percent: number;
  stage: string;
}

export interface GlossaryImportFrame {
  type: 'glossary_import';
  status: string;
  glossary_id: string;
  name: string;
  format: string;
  entry_count: number;
  warnings: string[];
}

export type WebSocketEnvelope =
  | ProgressFrame
  | BlockCompleteFrame
  | BlockRetryFrame
  | BlockRevisedFrame
  | PageCompleteFrame
  | QualitySummaryFrame
  | ChunkInitFrame
  | ChunkCompleteFrame
  | TranslateChunkCompleteFrame
  | CancelledFrame
  | GlossaryImportFrame
  | { type: string; [key: string]: unknown };

export type ToastLevel = 'info' | 'success' | 'warning' | 'error';

export interface Toast {
  id: string;
  level: ToastLevel;
  message: string;
  ttlMs: number;
  createdAt: number;
}

export interface AuthTokens {
  global?: string;
  ocr?: string;
  translation?: string;
  transcription?: string;
}

export interface ChunkSummary {
  chunk_idx: number;
  total_chunks: number;
  page_range: string;
  source_pages: number[];
  text_chars_so_far: number;
  overall_percent?: number;
}

export interface QualitySummary {
  scope: string;
  target: number;
  avg_confidence: number;
  repaired_count: number;
  below_target_count: number;
  page_idx?: number;
}

export interface JobState {
  activeJobId: string | null;
  percent: number;
  stage: string;
  statusMessage: string;
  warnings: string[];
  chunks: ChunkSummary[];
  failedPages: number[];
  completedPages: number[];
  qualitySummary: QualitySummary | null;
  isProcessing?: boolean;
}

export interface BBoxItem {
  block_id: string;
  page: number;
  block: number;
  /** Normalized [x0, y0, x1, y1] in 0..1 page coordinates. */
  bbox: number[];
  confidence: number | null;
  text: string;
  kind?: string;
  revised?: boolean;
  label?: string;
}

export type BoundingBox = BBoxItem;

export interface PageResult {
  page: number;
  width?: number;
  height?: number;
  bboxes?: BBoxItem[];
  text?: string;
  [key: string]: unknown;
}

export interface TrustSummary {
  block_count: number;
  scored_count: number;
  flagged_count: number;
  average: number;
  histogram: Record<string, number>;
  flag_counts: Record<string, number>;
}

export interface DocumentViewModel {
  pages: PageResult[];
  textArtifacts: TextArtifactHandle[];
  textArtifact?: TextArtifactHandle | null;
  textArtifactId?: string | null;
  textArtifactToken?: string | null;
  filename?: string | null;
  selectedPageIndex?: number;
  bboxes: BBoxItem[];
  confidence?: number;
  confidenceSummary: {
    average: number;
    min: number;
    max: number;
  };
  pageCount: number;
  trustSummary?: TrustSummary | null;
}

