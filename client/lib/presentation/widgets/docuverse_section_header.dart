import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// DocuVerse SectionHeader matching DESIGN_SYSTEM.md §4.6.
class DocuVerseSectionHeader extends StatelessWidget {
  const DocuVerseSectionHeader({
    super.key,
    required this.title,
    this.action,
    this.description,
  });

  final String title;
  final Widget? action;
  final String? description;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    title.toUpperCase(),
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontBody,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.8,
                      color: colors.foregroundMuted,
                    ),
                  ),
                  if (description != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      description!,
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontBody,
                        fontSize: 11,
                        color: colors.foregroundSubtle,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            if (action != null) action!,
          ],
        ),
        const SizedBox(height: 8),
        Divider(
          color: colors.border,
          height: 1,
          thickness: 1,
        ),
        const SizedBox(height: 12),
      ],
    );
  }
}
