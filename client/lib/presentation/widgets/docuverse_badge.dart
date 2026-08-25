import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

enum DocuVerseBadgeVariant {
  neutral,
  brand,
  success,
  warning,
  danger,
  info,
  revised,
}

enum DocuVerseBadgeSize {
  sm,
  md,
}

/// DocuVerse Badge primitive matching DESIGN_SYSTEM.md §4.4.
class DocuVerseBadge extends StatelessWidget {
  const DocuVerseBadge({
    super.key,
    required this.text,
    this.variant = DocuVerseBadgeVariant.neutral,
    this.size = DocuVerseBadgeSize.sm,
    this.icon,
    this.hasDot = false,
    this.onTap,
  });

  final String text;
  final DocuVerseBadgeVariant variant;
  final DocuVerseBadgeSize size;
  final Widget? icon;
  final bool hasDot;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    Color bg;
    Color fg;
    Color border;

    switch (variant) {
      case DocuVerseBadgeVariant.neutral:
        bg = colors.muted.withValues(alpha: 0.3);
        fg = colors.foregroundMuted;
        border = colors.borderStrong.withValues(alpha: 0.5);
        break;
      case DocuVerseBadgeVariant.brand:
        bg = colors.brand.withValues(alpha: 0.15);
        fg = colors.brand;
        border = colors.brand.withValues(alpha: 0.35);
        break;
      case DocuVerseBadgeVariant.success:
        bg = colors.success.withValues(alpha: 0.15);
        fg = colors.success;
        border = colors.success.withValues(alpha: 0.35);
        break;
      case DocuVerseBadgeVariant.warning:
        bg = colors.warning.withValues(alpha: 0.15);
        fg = colors.warning;
        border = colors.warning.withValues(alpha: 0.35);
        break;
      case DocuVerseBadgeVariant.danger:
        bg = colors.danger.withValues(alpha: 0.15);
        fg = colors.danger;
        border = colors.danger.withValues(alpha: 0.35);
        break;
      case DocuVerseBadgeVariant.info:
        bg = colors.info.withValues(alpha: 0.15);
        fg = colors.info;
        border = colors.info.withValues(alpha: 0.35);
        break;
      case DocuVerseBadgeVariant.revised:
        bg = colors.revisedCyan.withValues(alpha: 0.15);
        fg = colors.revisedCyan;
        border = colors.revisedCyan.withValues(alpha: 0.35);
        break;
    }

    final isSm = size == DocuVerseBadgeSize.sm;
    final height = isSm ? 20.0 : 24.0;
    final hPad = isSm ? 6.0 : 8.0;
    final fontSize = isSm ? 10.0 : 12.0;

    final badge = Container(
      height: height,
      padding: EdgeInsets.symmetric(horizontal: hPad),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(colors.badgeRadius),
        border: Border.all(color: border, width: 1.0),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          if (icon != null) ...[
            IconTheme(
              data: IconThemeData(size: isSm ? 10 : 12, color: fg),
              child: icon!,
            ),
            const SizedBox(width: 4),
          ],
          Text(
            text,
            style: TextStyle(
              fontFamily: DocuVerseTypography.fontMono,
              fontSize: fontSize,
              fontWeight: FontWeight.w600,
              color: fg,
              height: 1.0,
            ),
          ),
        ],
      ),
    );

    if (onTap == null) {
      return badge;
    }

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(colors.badgeRadius),
      child: badge,
    );
  }
}
