import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';

/// Speech-to-text Transcription View.
class TranscriptionView extends ConsumerStatefulWidget {
  const TranscriptionView({super.key});

  @override
  ConsumerState<TranscriptionView> createState() => _TranscriptionViewState();
}

class _TranscriptionViewState extends ConsumerState<TranscriptionView> {
  String _engine = 'whisper_api';
  String _language = 'auto';
  bool _isTranscribing = false;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Audio & Video Transcription',
                    style: AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Multi-speaker diarization and timestamped audio transcription powered by Whisper.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppBadge(
                label: 'Whisper Large-v3',
                variant: AppBadgeVariant.brand,
                size: AppBadgeSize.md,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Upload Area & Engine Selector
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Audio Upload Area
              Expanded(
                flex: 2,
                child: AppCard(
                  title: 'Media File',
                  subtitle: 'Upload MP3, WAV, MP4, M4A, OGG',
                  headerLeading: Icon(Icons.mic_none_outlined, size: 18, color: colors.brand),
                  child: Container(
                    height: 200,
                    decoration: BoxDecoration(
                      color: colors.background,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: colors.border, width: 1),
                    ),
                    child: Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.audio_file_outlined, size: 40, color: colors.brandAccent),
                          const SizedBox(height: 10),
                          Text(
                            'Drag & Drop Audio / Video File',
                            style: AppTypography.titleMedium(color: colors.textPrimary),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Maximum file size: 500MB',
                            style: AppTypography.bodySmall(color: colors.textMuted),
                          ),
                          const SizedBox(height: 14),
                          AppButton(
                            text: 'Select Audio File',
                            variant: AppButtonVariant.secondary,
                            size: AppButtonSize.sm,
                            onPressed: () {
                              ref.read(toastProvider.notifier).info('Selecting audio file...');
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 20),

              // Settings
              Expanded(
                flex: 1,
                child: AppCard(
                  title: 'Transcription Engine',
                  subtitle: 'Model parameters & language',
                  headerLeading: Icon(Icons.settings_voice_outlined, size: 18, color: colors.cyan),
                  child: Column(
                    children: [
                      AppSelect<String>(
                        label: 'Engine Type',
                        value: _engine,
                        items: const [
                          AppSelectItem(value: 'whisper_api', label: 'Whisper API (Cloud)'),
                          AppSelectItem(value: 'whisper_local', label: 'Whisper Local (GPU)'),
                          AppSelectItem(value: 'api', label: 'Custom Audio Endpoint'),
                        ],
                        onChanged: (v) {
                          if (v != null) setState(() => _engine = v);
                        },
                      ),
                      const SizedBox(height: 14),
                      AppSelect<String>(
                        label: 'Language',
                        value: _language,
                        items: const [
                          AppSelectItem(value: 'auto', label: 'Auto Detect'),
                          AppSelectItem(value: 'en', label: 'English'),
                          AppSelectItem(value: 'ar', label: 'Arabic'),
                          AppSelectItem(value: 'es', label: 'Spanish'),
                          AppSelectItem(value: 'fr', label: 'French'),
                        ],
                        onChanged: (v) {
                          if (v != null) setState(() => _language = v);
                        },
                      ),
                      const SizedBox(height: 14),
                      const AppInput(
                        label: 'Context Prompt / Glossary Hint',
                        placeholder: 'e.g. Medical terminology, names...',
                      ),
                      const SizedBox(height: 18),
                      AppButton(
                        text: _isTranscribing ? 'Transcribing...' : 'Start Transcription',
                        icon: const Icon(Icons.play_arrow_rounded),
                        variant: AppButtonVariant.primary,
                        size: AppButtonSize.md,
                        fullWidth: true,
                        loading: _isTranscribing,
                        onPressed: () {
                          setState(() => _isTranscribing = true);
                          Future.delayed(const Duration(seconds: 2), () {
                            if (mounted) {
                              setState(() => _isTranscribing = false);
                              ref.read(toastProvider.notifier).success('Transcription completed: 12 segments generated');
                            }
                          });
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Transcript Output Segments
          AppCard(
            title: 'Transcript Timeline',
            subtitle: 'Timestamped utterances with confidence scoring',
            headerLeading: Icon(Icons.subtitles_outlined, size: 18, color: colors.success),
            child: Column(
              children: [
                _buildSegmentRow('00:00 - 00:04', 'Speaker 1', 'Welcome to the OmniScribe technical overview session.', 0.98, colors),
                _buildSegmentRow('00:05 - 00:11', 'Speaker 2', 'Today we are presenting the new unified DocuVerse client architecture for desktop.', 0.95, colors),
                _buildSegmentRow('00:12 - 00:19', 'Speaker 1', 'Notice how the grounding confidence scores dynamically map in real time.', 0.92, colors),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSegmentRow(String time, String speaker, String text, double score, AppColorScheme colors) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: colors.cardRaised,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: colors.border, width: 1),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
            decoration: BoxDecoration(
              color: colors.muted,
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(time, style: AppTypography.codeSmall(color: colors.textPrimary)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(speaker, style: AppTypography.captionStrong(color: colors.brandAccent)),
                const SizedBox(height: 3),
                Text(text, style: AppTypography.bodyMedium(color: colors.textPrimary)),
              ],
            ),
          ),
          const SizedBox(width: 12),
          AppBadge(
            label: '${(score * 100).toInt()}%',
            variant: AppBadgeVariant.success,
            size: AppBadgeSize.sm,
          ),
        ],
      ),
    );
  }
}
