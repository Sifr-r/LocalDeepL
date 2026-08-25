import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// DocuVerse Toggle switch row with label, description, and state matching DESIGN_SYSTEM.md §4.3.
class DocuVerseToggle extends StatelessWidget {
  const DocuVerseToggle({
    super.key,
    required this.label,
    this.description,
    required this.checked,
    required this.onChanged,
    this.badge,
  });

  final String label;
  final String? description;
  final bool checked;
  final ValueChanged<bool> onChanged;
  final Widget? badge;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    return InkWell(
      onTap: () => onChanged(!checked),
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6.0, horizontal: 4.0),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Text(
                        label,
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontBody,
                          fontSize: 13,
                          fontWeight: FontWeight.w500,
                          color: colors.foreground,
                        ),
                      ),
                      if (badge != null) ...[
                        const SizedBox(width: 8),
                        badge!,
                      ],
                    ],
                  ),
                  if (description != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      description!,
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontBody,
                        fontSize: 11,
                        color: colors.foregroundMuted,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            const SizedBox(width: 12),
            SizedBox(
              height: 24,
              child: Switch(
                value: checked,
                onChanged: onChanged,
                materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
