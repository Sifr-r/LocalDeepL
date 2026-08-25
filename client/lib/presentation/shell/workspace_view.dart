import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/providers/settings_notifier.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/providers/provider_modal.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';

class WorkspaceView extends ConsumerWidget {
  const WorkspaceView({super.key, required this.onNavigateTab});

  final ValueChanged<int> onNavigateTab;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final settings = ref.watch(settingsStateProvider);
    final tokens = context.docuVerse;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 1000),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Hero Banner
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(28),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    colors: [
                      tokens.brand.withValues(alpha: 0.2),
                      tokens.card,
                    ],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  borderRadius: BorderRadius.circular(tokens.radiusCard + 4),
                  border: Border.all(color: tokens.brand.withValues(alpha: 0.3)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8),
                          decoration: BoxDecoration(
                            color: tokens.brand,
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: const Icon(Icons.document_scanner, color: Colors.white, size: 24),
                        ),
                        const SizedBox(width: 14),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'OmniScribe AI Document Suite',
                              style: TextStyle(
                                fontSize: 24,
                                fontWeight: FontWeight.bold,
                                color: tokens.foreground,
                                letterSpacing: -0.5,
                              ),
                            ),
                            Text(
                              'Universal Document OCR, Neural Translation, Voice Transcription & Schema Extraction',
                              style: TextStyle(fontSize: 13, color: tokens.foregroundMuted),
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                    Wrap(
                      spacing: 12,
                      runSpacing: 8,
                      children: [
                        DocuVerseBadge(text: 'Active Provider: ${settings.activeProviderId.toUpperCase()}',
                          variant: DocuVerseBadgeVariant.brand,
                        ),
                        DocuVerseBadge(text: 'Model: ${settings.runtimeConfig?.model ?? 'auto'}',
                          variant: DocuVerseBadgeVariant.neutral,
                        ),
                        DocuVerseBadge(text: 'Server: Offline',
                          variant: DocuVerseBadgeVariant.danger,
                          hasDot: true,
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              Text(
                'AI WORKSPACES & MODULES',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: tokens.foregroundMuted,
                  letterSpacing: 0.8,
                ),
              ),
              const SizedBox(height: 12),

              // Feature Cards Grid
              GridView.count(
                crossAxisCount: 2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                mainAxisSpacing: 16,
                crossAxisSpacing: 16,
                childAspectRatio: 1.8,
                children: [
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.translate,
                    title: 'Neural Translation',
                    description: 'Dual-engine document translation with term preservation & sliding window context.',
                    badge: 'LangGraph / NLLB',
                    onTap: () => onNavigateTab(1),
                  ),
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.mic,
                    title: 'Voice Transcription',
                    description: 'Whisper-powered acoustic transcription with interactive timestamped segments.',
                    badge: 'Whisper / Local',
                    onTap: () => onNavigateTab(2),
                  ),
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.menu_book,
                    title: 'Terminology Glossary',
                    description: 'Domain lexicons, term overrides, and dictionary mappings for high-precision OCR.',
                    badge: 'Multi-Format',
                    onTap: () => onNavigateTab(3),
                  ),
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.schema,
                    title: 'Structured Extraction',
                    description: 'Extract strongly-typed entities, tables, invoices, and JSON schemas from documents.',
                    badge: 'AST / JSON',
                    onTap: () => onNavigateTab(4),
                  ),
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.history,
                    title: 'Job Execution History',
                    description: 'Audit log of past OCR pipeline jobs with searchable PDF downloads.',
                    badge: 'Audit Log',
                    onTap: () => onNavigateTab(5),
                  ),
                  _buildWorkspaceCard(
                    context: context,
                    icon: Icons.settings,
                    title: 'System Settings',
                    description: 'Configure LLM inference providers, endpoints, concurrency, and security tokens.',
                    badge: 'Config',
                    onTap: () => onNavigateTab(6),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildWorkspaceCard({
    required BuildContext context,
    required IconData icon,
    required String title,
    required String description,
    required String badge,
    required VoidCallback onTap,
  }) {
    final tokens = context.docuVerse;

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(tokens.radiusCard),
      child: DocuVerseCard(
        padding: DocuVerseCardPadding.md,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: tokens.cardRaised,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: tokens.border),
                  ),
                  child: Icon(icon, size: 18, color: tokens.brand),
                ),
                DocuVerseBadge(text: badge, variant: DocuVerseBadgeVariant.neutral),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: tokens.foreground,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: TextStyle(fontSize: 12, color: tokens.foregroundMuted),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
