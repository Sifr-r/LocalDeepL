import 'package:flutter/material.dart';
import 'package:omniscribe_client/data/models/provider_preset.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';

class ProviderCard extends StatefulWidget {
  const ProviderCard({
    super.key,
    required this.provider,
    required this.models,
    required this.isLoadingModels,
    required this.onConnect,
    required this.onUseModel,
    required this.onRefreshModels,
    this.isActive = false,
  });

  final ProviderPreset provider;
  final List<String> models;
  final bool isLoadingModels;
  final VoidCallback onConnect;
  final ValueChanged<String> onUseModel;
  final VoidCallback onRefreshModels;
  final bool isActive;

  @override
  State<ProviderCard> createState() => _ProviderCardState();
}

class _ProviderCardState extends State<ProviderCard> {
  bool _isExpanded = false;

  IconData _getProviderIcon(String id) {
    final lower = id.toLowerCase();
    if (lower.contains('openai')) return Icons.auto_awesome;
    if (lower.contains('anthropic') || lower.contains('claude')) {
      return Icons.psychology;
    }
    if (lower.contains('ollama')) return Icons.terminal;
    if (lower.contains('lmstudio')) return Icons.desktop_windows;
    if (lower.contains('openrouter')) return Icons.alt_route;
    if (lower.contains('groq')) return Icons.bolt;
    if (lower.contains('deepseek')) return Icons.explore;
    if (lower.contains('azure')) return Icons.cloud;
    if (lower.contains('vllm')) return Icons.memory;
    return Icons.hub;
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.docuVerse;
    final effectiveModels =
        widget.models.isNotEmpty ? widget.models : widget.provider.models;

    return Container(
      decoration: BoxDecoration(
        color: tokens.cardRaised,
        borderRadius: BorderRadius.circular(tokens.radiusCard),
        border: Border.all(
          color: widget.isActive ? tokens.brand : tokens.border,
          width: widget.isActive ? 1.5 : 1,
        ),
      ),
      padding: const EdgeInsets.all(14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Top Row: Icon + Name + Badges + Connect Button
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: tokens.card,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: tokens.borderStrong),
                ),
                child: Icon(
                  _getProviderIcon(widget.provider.id),
                  size: 18,
                  color: widget.isActive ? tokens.brand : tokens.foreground,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            widget.provider.name,
                            style: TextStyle(
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                              color: tokens.foreground,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (widget.isActive) ...[
                          const SizedBox(width: 6),
                          const DocuVerseBadge(
                            text: 'Active',
                            variant: DocuVerseBadgeVariant.brand,
                            hasDot: true,
                          ),
                        ],
                        if (widget.provider.isRecommended ?? false) ...[
                          const SizedBox(width: 6),
                          const DocuVerseBadge(
                            text: 'Recommended',
                            variant: DocuVerseBadgeVariant.info,
                          ),
                        ],
                        if (!widget.provider.requiresKey) ...[
                          const SizedBox(width: 6),
                          const DocuVerseBadge(
                            text: 'Local',
                            variant: DocuVerseBadgeVariant.success,
                          ),
                        ],
                        if (widget.provider.isCustom ?? false) ...[
                          const SizedBox(width: 6),
                          const DocuVerseBadge(
                            text: 'Custom',
                            variant: DocuVerseBadgeVariant.warning,
                          ),
                        ],
                      ],
                    ),
                    if (widget.provider.description.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        widget.provider.description,
                        style: TextStyle(
                          fontSize: 11,
                          color: tokens.foregroundMuted,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DocuVerseButton(
                    onPressed:
                        widget.isLoadingModels ? null : widget.onRefreshModels,
                    variant: DocuVerseButtonVariant.ghost,
                    size: DocuVerseButtonSize.sm,
                    icon: Icon(
                      Icons.refresh,
                      size: 14,
                      color: tokens.foregroundMuted,
                    ),
                    tooltip: 'Refresh models',
                  ),
                  const SizedBox(width: 4),
                  DocuVerseButton(
                    text: widget.isActive ? 'Configure' : 'Connect',
                    onPressed: widget.onConnect,
                    variant: widget.isActive
                        ? DocuVerseButtonVariant.primary
                        : DocuVerseButtonVariant.secondary,
                    size: DocuVerseButtonSize.sm,
                  ),
                ],
              ),
            ],
          ),

          // Models Section
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: tokens.card,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: tokens.border.withValues(alpha: 0.5)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                InkWell(
                  onTap: () {
                    setState(() {
                      _isExpanded = !_isExpanded;
                    });
                  },
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Row(
                        children: [
                          if (widget.isLoadingModels) ...[
                            SizedBox(
                              width: 12,
                              height: 12,
                              child: CircularProgressIndicator(
                                strokeWidth: 1.5,
                                valueColor:
                                    AlwaysStoppedAnimation<Color>(tokens.brand),
                              ),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              'Discovering models…',
                              style: TextStyle(
                                  fontSize: 11, color: tokens.foregroundMuted),
                            ),
                          ] else ...[
                            Text(
                              '${effectiveModels.length} models available',
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                                color: tokens.foregroundMuted,
                              ),
                            ),
                            if (widget.provider.defaultModel.isNotEmpty) ...[
                              Text(
                                ' (default: ${widget.provider.defaultModel})',
                                style: TextStyle(
                                  fontSize: 11,
                                  color: tokens.foregroundSubtle,
                                ),
                              ),
                            ],
                          ],
                        ],
                      ),
                      Icon(
                        _isExpanded
                            ? Icons.keyboard_arrow_up
                            : Icons.keyboard_arrow_down,
                        size: 16,
                        color: tokens.foregroundMuted,
                      ),
                    ],
                  ),
                ),
                if (_isExpanded && effectiveModels.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Divider(color: tokens.border, height: 1),
                  const SizedBox(height: 6),
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 140),
                    child: ListView.separated(
                      shrinkWrap: true,
                      itemCount: effectiveModels.length,
                      separatorBuilder: (_, __) => const SizedBox(height: 4),
                      itemBuilder: (context, index) {
                        final modelName = effectiveModels[index];
                        return Row(
                          children: [
                            Expanded(
                              child: Text(
                                modelName,
                                style: TextStyle(
                                  fontSize: 11,
                                  fontFamily: 'monospace',
                                  color: tokens.foreground,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            InkWell(
                              onTap: () => widget.onUseModel(modelName),
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 6, vertical: 2),
                                child: Text(
                                  'Use',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    color: tokens.brand,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        );
                      },
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
