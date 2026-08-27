import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/data/models/feature_models.dart';
import 'package:omniscribe_client/data/providers/features_notifier.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/section_header.dart';

class TranscriptionScreen extends ConsumerStatefulWidget {
  const TranscriptionScreen({super.key});

  @override
  ConsumerState<TranscriptionScreen> createState() =>
      _TranscriptionScreenState();
}

class _TranscriptionScreenState extends ConsumerState<TranscriptionScreen> {
  late final TextEditingController _modelController;
  late final TextEditingController _languageController;
  late final TextEditingController _promptController;

  @override
  void initState() {
    super.initState();
    final config = ref.read(settingsStateProvider).runtimeConfig;
    final transcriptionState = ref.read(transcriptionProvider);

    _modelController = TextEditingController(
      text: transcriptionState.model.isNotEmpty
          ? transcriptionState.model
          : (config?.transcriptionModel ?? 'whisper-1'),
    );
    _languageController = TextEditingController(
      text: transcriptionState.language ??
          (config?.transcriptionLanguage ?? ''),
    );
    _promptController = TextEditingController(
      text: transcriptionState.prompt ??
          (config?.transcriptionPrompt ?? ''),
    );
  }

  @override
  void dispose() {
    _modelController.dispose();
    _languageController.dispose();
    _promptController.dispose();
    super.dispose();
  }

  void _pickSampleAudioFile() {
    final mockBytes =
        Uint8List.fromList(utf8.encode('RIFF....WAVEfmt ....data....'));
    ref.read(transcriptionProvider.notifier).setAudio(
          mockBytes,
          'interview_recording_sample.wav',
          duration: 45.0,
        );
  }

  Future<void> _handleTranscribe() async {
    final state = ref.read(transcriptionProvider);
    if (state.audioBytes == null || state.audioFilename == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select an audio file first.')),
      );
      return;
    }

    final notifier = ref.read(transcriptionProvider.notifier);
    notifier.setModel(_modelController.text.trim());
    notifier.setLanguage(_languageController.text.trim());
    notifier.setPrompt(_promptController.text.trim());

    final config = ref.read(settingsStateProvider).runtimeConfig;
    await notifier.transcribe(
      apiBase: config?.transcriptionApiBase ?? config?.apiBase,
      apiKey: config?.transcriptionApiKey ?? config?.apiKey,
    );
  }

  void _togglePlayback() {
    ref.read(transcriptionProvider.notifier).togglePlayback();
  }

  void _seekToSegment(TranscriptionSegment segment) {
    ref.read(transcriptionProvider.notifier).seekToSegment(segment);
  }

  void _exportTxt(TranscriptionResponse? result) {
    if (result == null) return;
    unawaited(Clipboard.setData(ClipboardData(text: result.text)));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Transcript copied to clipboard.')),
    );
  }

  void _exportSrt(TranscriptionResponse? result) {
    if (result == null) return;
    final buffer = StringBuffer();
    for (int i = 0; i < result.segments.length; i++) {
      final seg = result.segments[i];
      buffer.writeln('${i + 1}');
      buffer.writeln(
        '${_formatSrtTime(seg.start)} --> ${_formatSrtTime(seg.end)}',
      );
      buffer.writeln(seg.text);
      buffer.writeln();
    }
    unawaited(Clipboard.setData(ClipboardData(text: buffer.toString())));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('SRT Subtitles copied to clipboard.')),
    );
  }

  String _formatSrtTime(double seconds) {
    final hrs = (seconds / 3600).floor().toString().padLeft(2, '0');
    final mins = ((seconds % 3600) / 60).floor().toString().padLeft(2, '0');
    final secs = (seconds % 60).floor().toString().padLeft(2, '0');
    final ms =
        ((seconds - seconds.floor()) * 1000).floor().toString().padLeft(3, '0');
    return '$hrs:$mins:$secs,$ms';
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(transcriptionProvider);
    final notifier = ref.read(transcriptionProvider.notifier);
    final colors = context.colors;

    return Scaffold(
      backgroundColor: colors.background,
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header Bar
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          'Voice & Audio Transcription',
                          style: AppTypography.displaySmall(
                            color: colors.textPrimary,
                          ),
                        ),
                        const SizedBox(width: 10),
                        const AppBadge(
                          label: 'Whisper / Faster-Whisper',
                          variant: AppBadgeVariant.brand,
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Transcribe speech with timestamped segments and interactive audio player simulation',
                      style: AppTypography.bodySmall(
                        color: colors.textMuted,
                      ),
                    ),
                  ],
                ),
                SizedBox(
                  width: 220,
                  child: AppSelect<String>(
                    value: state.engine,
                    items: const [
                      AppSelectItem(
                        value: 'api',
                        label: 'OpenAI / Remote API',
                      ),
                      AppSelectItem(
                        value: 'faster-whisper',
                        label: 'Faster-Whisper (Local)',
                      ),
                    ],
                    onChanged: (val) {
                      if (val != null) {
                        notifier.setEngine(val);
                      }
                    },
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Main Content: Left Column (Audio Upload + Controls) and Right Column (Segments)
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Left Pane (1/3 width)
                  SizedBox(
                    width: 340,
                    child: AppCard(
                      padding: AppCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const SectionHeader(
                            title: 'Audio File & Controls',
                          ),
                          const SizedBox(height: 8),
                          // Dropzone / File Picker Container
                          InkWell(
                            onTap: _pickSampleAudioFile,
                            borderRadius: BorderRadius.circular(6),
                            child: Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(16),
                              decoration: BoxDecoration(
                                color: colors.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(
                                  color: state.audioFilename != null
                                      ? colors.brand
                                      : colors.border,
                                  style: BorderStyle.solid,
                                ),
                              ),
                              child: Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    state.audioFilename != null
                                        ? Icons.audio_file
                                        : Icons.cloud_upload_outlined,
                                    size: 32,
                                    color: state.audioFilename != null
                                        ? colors.brand
                                        : colors.textMuted,
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    state.audioFilename ??
                                        'Click to load audio file',
                                    style: AppTypography.labelMedium(
                                      color: colors.textPrimary,
                                    ).copyWith(fontWeight: FontWeight.w600),
                                    textAlign: TextAlign.center,
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    state.audioFilename != null
                                        ? 'Duration: ${state.totalDuration.toStringAsFixed(1)}s'
                                        : 'Supports WAV, MP3, M4A, FLAC, OGG',
                                    style: AppTypography.codeSmall(
                                      color: colors.textMuted,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                          const SizedBox(height: 14),

                          // Simulated Audio Player
                          if (state.audioFilename != null) ...[
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: colors.cardRaised,
                                borderRadius: BorderRadius.circular(6),
                                border: Border.all(color: colors.border),
                              ),
                              child: Column(
                                children: [
                                  Row(
                                    children: [
                                      IconButton(
                                        icon: Icon(
                                          state.isPlaying
                                              ? Icons.pause_circle_filled
                                              : Icons.play_circle_filled,
                                          size: 28,
                                          color: colors.brand,
                                        ),
                                        onPressed: _togglePlayback,
                                      ),
                                      const SizedBox(width: 8),
                                      Expanded(
                                        child: SliderTheme(
                                          data: SliderThemeData(
                                            trackHeight: 3,
                                            thumbShape:
                                                const RoundSliderThumbShape(
                                              enabledThumbRadius: 6,
                                            ),
                                            overlayShape:
                                                const RoundSliderOverlayShape(
                                              overlayRadius: 10,
                                            ),
                                            activeTrackColor: colors.brand,
                                            inactiveTrackColor:
                                                colors.borderStrong,
                                            thumbColor: colors.brand,
                                          ),
                                          child: Slider(
                                            value: state.currentPlaybackTime
                                                .clamp(
                                              0.0,
                                              state.totalDuration > 0
                                                  ? state.totalDuration
                                                  : 1.0,
                                            ),
                                            max: state.totalDuration > 0
                                                ? state.totalDuration
                                                : 1.0,
                                            onChanged: (val) {
                                              notifier.setPlaybackTime(val);
                                            },
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                  Row(
                                    mainAxisAlignment:
                                        MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        '${state.currentPlaybackTime.toStringAsFixed(1)}s',
                                        style: AppTypography.codeSmall(
                                          color: colors.textMuted,
                                        ),
                                      ),
                                      Text(
                                        '${state.totalDuration.toStringAsFixed(1)}s',
                                        style: AppTypography.codeSmall(
                                          color: colors.textMuted,
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 14),
                          ],

                          // Inputs
                          AppInput(
                            controller: _modelController,
                            label: 'Model ID',
                            placeholder: 'whisper-1',
                            monospace: true,
                          ),
                          const SizedBox(height: 10),
                          AppInput(
                            controller: _languageController,
                            label: 'Language (ISO Code)',
                            placeholder:
                                'Auto-detect if blank (e.g. en, fr, de)',
                          ),
                          const SizedBox(height: 10),
                          AppInput(
                            controller: _promptController,
                            label: 'Glossary / Vocabulary Prompt',
                            placeholder: 'Optional domain terms...',
                            maxLines: 2,
                          ),
                          const Spacer(),

                          AppButton(
                            text: state.isTranscribing
                                ? 'Transcribing…'
                                : 'Start Transcription',
                            variant: AppButtonVariant.primary,
                            fullWidth: true,
                            loading: state.isTranscribing,
                            disabled: state.audioBytes == null,
                            icon: const Icon(Icons.mic, size: 16),
                            onPressed: _handleTranscribe,
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),

                  // Right Pane: Timestamped Segments
                  Expanded(
                    child: AppCard(
                      padding: AppCardPadding.md,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          SectionHeader(
                            title: 'Transcription Segments',
                            action: state.result != null &&
                                    state.result!.segments.isNotEmpty
                                ? Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      AppButton(
                                        text: 'Export .TXT',
                                        variant: AppButtonVariant.ghost,
                                        size: AppButtonSize.sm,
                                        onPressed: () =>
                                            _exportTxt(state.result),
                                      ),
                                      const SizedBox(width: 6),
                                      AppButton(
                                        text: 'Export .SRT',
                                        variant:
                                            AppButtonVariant.secondary,
                                        size: AppButtonSize.sm,
                                        onPressed: () =>
                                            _exportSrt(state.result),
                                      ),
                                    ],
                                  )
                                : null,
                          ),
                          const SizedBox(height: 8),
                          Expanded(
                            child: state.isTranscribing
                                ? Center(
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        CircularProgressIndicator(
                                          valueColor:
                                              AlwaysStoppedAnimation<Color>(
                                            colors.brand,
                                          ),
                                        ),
                                        const SizedBox(height: 12),
                                        Text(
                                          'Processing audio waveform & extracting tokens…',
                                          style: AppTypography.bodySmall(
                                            color: colors.textMuted,
                                          ),
                                        ),
                                      ],
                                    ),
                                  )
                                : (state.result == null ||
                                        state.result!.segments.isEmpty)
                                    ? Center(
                                        child: Text(
                                          'Select an audio file and click "Start Transcription" to view interactive segments.',
                                          style: AppTypography.bodySmall(
                                            color: colors.textMuted,
                                          ),
                                        ),
                                      )
                                    : ListView.separated(
                                        itemCount: state.result!.segments.length,
                                        separatorBuilder: (_, __) =>
                                            const SizedBox(height: 8),
                                        itemBuilder: (context, index) {
                                          final segment =
                                              state.result!.segments[index];
                                          final isActive =
                                              state.activeSegmentId ==
                                                      segment.id ||
                                                  (state.currentPlaybackTime >=
                                                          segment.start &&
                                                      state.currentPlaybackTime <=
                                                          segment.end);

                                          return InkWell(
                                            onTap: () =>
                                                _seekToSegment(segment),
                                            borderRadius:
                                                BorderRadius.circular(6),
                                            child: AnimatedContainer(
                                              duration: const Duration(
                                                milliseconds: 150,
                                              ),
                                              padding: const EdgeInsets.all(12),
                                              decoration: BoxDecoration(
                                                color: isActive
                                                    ? colors.brand
                                                        .withValues(alpha: 0.15)
                                                    : colors.cardRaised,
                                                borderRadius:
                                                    BorderRadius.circular(6),
                                                border: Border.all(
                                                  color: isActive
                                                      ? colors.brand
                                                      : colors.border,
                                                ),
                                              ),
                                              child: Row(
                                                crossAxisAlignment:
                                                    CrossAxisAlignment.start,
                                                children: [
                                                  Container(
                                                    padding: const EdgeInsets
                                                        .symmetric(
                                                      horizontal: 6,
                                                      vertical: 2,
                                                    ),
                                                    decoration: BoxDecoration(
                                                      color: isActive
                                                          ? colors.brand
                                                          : colors.card,
                                                      borderRadius:
                                                          BorderRadius.circular(
                                                        4,
                                                      ),
                                                    ),
                                                    child: Text(
                                                      '${segment.start.toStringAsFixed(1)}s - ${segment.end.toStringAsFixed(1)}s',
                                                      style: TextStyle(
                                                        fontSize: 10,
                                                        fontFamily: 'monospace',
                                                        fontWeight:
                                                            FontWeight.bold,
                                                        color: isActive
                                                            ? colors
                                                                .brandForeground
                                                            : colors.brand,
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(width: 12),
                                                  Expanded(
                                                    child: Text(
                                                      segment.text,
                                                      style: AppTypography.bodySmall(
                                                        color: colors.textPrimary,
                                                      ).copyWith(height: 1.4),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          );
                                        },
                                      ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
