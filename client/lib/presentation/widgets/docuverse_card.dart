import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

enum DocuVerseCardVariant {
  defaultCard,
  raised,
  inset,
}

enum DocuVerseCardPadding {
  none,
  sm,
  md,
  lg,
}

/// Universal DocuVerse Card surface primitive matching DESIGN_SYSTEM.md §4.2.
class DocuVerseCard extends StatelessWidget {
  const DocuVerseCard({
    super.key,
    required this.child,
    this.variant = DocuVerseCardVariant.defaultCard,
    this.padding = DocuVerseCardPadding.md,
    this.borderRadius,
    this.borderColor,
    this.backgroundColor,
    this.width,
    this.height,
  });

  final Widget child;
  final DocuVerseCardVariant variant;
  final DocuVerseCardPadding padding;
  final BorderRadius? borderRadius;
  final Color? borderColor;
  final Color? backgroundColor;
  final double? width;
  final double? height;

  EdgeInsets get _paddingInsets {
    switch (padding) {
      case DocuVerseCardPadding.none:
        return EdgeInsets.zero;
      case DocuVerseCardPadding.sm:
        return const EdgeInsets.all(12.0);
      case DocuVerseCardPadding.md:
        return const EdgeInsets.all(16.0);
      case DocuVerseCardPadding.lg:
        return const EdgeInsets.all(24.0);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    Color bg;
    Border? border;

    switch (variant) {
      case DocuVerseCardVariant.defaultCard:
        bg = backgroundColor ?? colors.card;
        border = Border.all(
          color: borderColor ?? colors.border,
          width: 1.0,
        );
        break;
      case DocuVerseCardVariant.raised:
        bg = backgroundColor ?? colors.cardRaised;
        border = Border.all(
          color: borderColor ?? colors.border,
          width: 1.0,
        );
        break;
      case DocuVerseCardVariant.inset:
        bg = backgroundColor ?? colors.cardRaised;
        border = null;
        break;
    }

    final radius = borderRadius ?? BorderRadius.circular(colors.cardRadius);

    return Container(
      width: width,
      height: height,
      padding: _paddingInsets,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: radius,
        border: border,
      ),
      child: child,
    );
  }
}
