import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/data/models/bbox_item.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_card.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_section_header.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// Detail inspector panel for the currently selected bounding box.
class BBoxInspector extends ConsumerStatefulWidget {
  const BBoxInspector({
    super.key,
    required this.bbox,
    this.onClose,
  });

  final BBoxItem bbox;
  final VoidCallback? onClose;

  @override
  ConsumerState<BBoxInspector> createState() => _BBoxInspectorState();
}

class _BBoxInspectorState extends ConsumerState<BBoxInspector> {
  late TextEditingController _textController;
  bool _isEditing = false;
  bool _hasCopied = false;

  @override
  void initState() {
    super.initState();
    _textController = TextEditingController(text: widget.bbox.text);
  }

  @override
  void didUpdateWidget(covariant BBoxInspector oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.bbox.blockId != widget.bbox.blockId ||
        oldWidget.bbox.text != widget.bbox.text) {
      _textController.text = widget.bbox.text;
      _isEditing = false;
    }
  }

  @override
  void dispose() {
    _textController.dispose();
    super.dispose();
  }

  void _copyText() {
    Clipboard.setData(ClipboardData(text: _textController.text));
    setState(() {
      _hasCopied = true;
    });
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _hasCopied = false;
        });
      }
    });
  }

  void _saveEdits() {
    final notifier = ref.read(workstationProvider.notifier);
    final updated = widget.bbox.copyWith(
      text: _textController.text,
      revised: true,
    );
    notifier.addOrUpdateBBox(widget.bbox.page, updated);
    setState(() {
      _isEditing = false;
    });
  }

  void _changeKind(String? newKind) {
    if (newKind == null) return;
    final notifier = ref.read(workstationProvider.notifier);
    final updated = widget.bbox.copyWith(kind: newKind);
    notifier.addOrUpdateBBox(widget.bbox.page, updated);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final bbox = widget.bbox;

    DocuVerseBadgeVariant confBadgeVariant;
    if (bbox.confidence == null) {
      confBadgeVariant = DocuVerseBadgeVariant.neutral;
    } else if (bbox.confidence! >= 0.85) {
      confBadgeVariant = DocuVerseBadgeVariant.success;
    } else if (bbox.confidence! >= 0.60) {
      confBadgeVariant = DocuVerseBadgeVariant.warning;
    } else {
      confBadgeVariant = DocuVerseBadgeVariant.danger;
    }

    return DocuVerseCard(
      variant: DocuVerseCardVariant.defaultCard,
      padding: DocuVerseCardPadding.md,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Header with Block ID and Close Button
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.layers_outlined, size: 16, color: colors.brand),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        'Bounding Box Inspector',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontDisplay,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: colors.foreground,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close_rounded, size: 18),
                color: colors.foregroundMuted,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
                tooltip: 'Close Inspector',
                onPressed: widget.onClose,
              ),
            ],
          ),
          const SizedBox(height: 12),

          // Metadata Chips Row (ID, Conf, Revision)
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              DocuVerseBadge(
                text: bbox.blockId,
                variant: DocuVerseBadgeVariant.brand,
                size: DocuVerseBadgeSize.sm,
              ),
              DocuVerseBadge(
                text: bbox.confidencePercent != null
                    ? '${bbox.confidencePercent}% CONF'
                    : 'NO CONF',
                variant: confBadgeVariant,
                size: DocuVerseBadgeSize.sm,
              ),
              if (bbox.isRevised)
                const DocuVerseBadge(
                  text: 'REVISED',
                  variant: DocuVerseBadgeVariant.revised,
                  size: DocuVerseBadgeSize.sm,
                ),
            ],
          ),
          const SizedBox(height: 12),

          // Block Kind & Coordinates
          const DocuVerseSectionHeader(title: 'Block Properties'),
          Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Block Kind',
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontBody,
                        fontSize: 11,
                        color: colors.foregroundMuted,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      decoration: BoxDecoration(
                        color: colors.cardRaised,
                        borderRadius: BorderRadius.circular(colors.radiusInput),
                        border: Border.all(color: colors.border),
                      ),
                      child: DropdownButtonHideUnderline(
                        child: DropdownButton<String>(
                          value: bbox.kind ?? 'paragraph',
                          isExpanded: true,
                          dropdownColor: colors.cardRaised,
                          icon: Icon(Icons.arrow_drop_down,
                              size: 18, color: colors.foregroundMuted),
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontBody,
                            fontSize: 12,
                            fontWeight: FontWeight.w500,
                            color: colors.foreground,
                          ),
                          items: const [
                            DropdownMenuItem(
                                value: 'paragraph', child: Text('Paragraph')),
                            DropdownMenuItem(
                                value: 'heading', child: Text('Heading')),
                            DropdownMenuItem(
                                value: 'title', child: Text('Title')),
                            DropdownMenuItem(
                                value: 'table', child: Text('Table')),
                            DropdownMenuItem(
                                value: 'list_item', child: Text('List Item')),
                            DropdownMenuItem(
                                value: 'caption', child: Text('Caption')),
                            DropdownMenuItem(
                                value: 'code', child: Text('Code')),
                            DropdownMenuItem(
                                value: 'formula', child: Text('Formula')),
                            DropdownMenuItem(
                                value: 'header', child: Text('Header')),
                            DropdownMenuItem(
                                value: 'footer', child: Text('Footer')),
                          ],
                          onChanged: _changeKind,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Dimensions (W × H)',
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontBody,
                        fontSize: 11,
                        color: colors.foregroundMuted,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Container(
                      height: 36,
                      alignment: Alignment.centerLeft,
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      decoration: BoxDecoration(
                        color: colors.cardRaised,
                        borderRadius: BorderRadius.circular(colors.radiusInput),
                        border: Border.all(color: colors.border),
                      ),
                      child: Text(
                        '${(bbox.width * 100).toStringAsFixed(1)}% × ${(bbox.height * 100).toStringAsFixed(1)}%',
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontMono,
                          fontSize: 11,
                          color: colors.foreground,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),

          // Normalized Bounding Box Coordinate Pill
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
            decoration: BoxDecoration(
              color: colors.cardRaised.withValues(alpha: 0.6),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: colors.border),
            ),
            child: Row(
              children: [
                Icon(Icons.crop_free_rounded,
                    size: 12, color: colors.foregroundSubtle),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'bbox: [${bbox.x0.toStringAsFixed(3)}, ${bbox.y0.toStringAsFixed(3)}, ${bbox.x1.toStringAsFixed(3)}, ${bbox.y1.toStringAsFixed(3)}]',
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontMono,
                      fontSize: 10,
                      color: colors.foregroundSubtle,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // OCR Extracted Text Section
          DocuVerseSectionHeader(
            title: 'Extracted Content',
            action: InkWell(
              onTap: _copyText,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    _hasCopied
                        ? Icons.check_rounded
                        : Icons.content_copy_rounded,
                    size: 12,
                    color: _hasCopied ? colors.success : colors.brand,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    _hasCopied ? 'Copied' : 'Copy Text',
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontBody,
                      fontSize: 11,
                      fontWeight: FontWeight.w500,
                      color: _hasCopied ? colors.success : colors.brand,
                    ),
                  ),
                ],
              ),
            ),
          ),

          // Text Content Box / Editor
          Container(
            decoration: BoxDecoration(
              color: colors.cardRaised,
              borderRadius: BorderRadius.circular(colors.radiusInput),
              border: Border.all(color: colors.borderStrong),
            ),
            child: TextField(
              controller: _textController,
              maxLines: 4,
              minLines: 3,
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontBody,
                fontSize: 13,
                height: 1.4,
                color: colors.foreground,
              ),
              onChanged: (_) {
                if (!_isEditing) {
                  setState(() {
                    _isEditing = true;
                  });
                }
              },
              decoration: InputDecoration(
                contentPadding: const EdgeInsets.all(10),
                border: InputBorder.none,
                hintText: 'OCR text content...',
                hintStyle: TextStyle(
                  fontFamily: DocuVerseTypography.fontBody,
                  fontSize: 12,
                  color: colors.foregroundSubtle,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),

          // Action Buttons Footer
          if (_isEditing) ...[
            Row(
              children: [
                Expanded(
                  child: DocuVerseButton(
                    text: 'Save Edits',
                    variant: DocuVerseButtonVariant.primary,
                    size: DocuVerseButtonSize.sm,
                    icon: const Icon(Icons.check, size: 14),
                    onPressed: _saveEdits,
                  ),
                ),
                const SizedBox(width: 8),
                DocuVerseButton(
                  text: 'Cancel',
                  variant: DocuVerseButtonVariant.ghost,
                  size: DocuVerseButtonSize.sm,
                  onPressed: () {
                    _textController.text = widget.bbox.text;
                    setState(() {
                      _isEditing = false;
                    });
                  },
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
