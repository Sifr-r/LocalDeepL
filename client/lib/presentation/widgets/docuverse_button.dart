import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

enum DocuVerseButtonVariant {
  primary,
  secondary,
  ghost,
  danger,
  outline,
}

enum DocuVerseButtonSize {
  sm,
  md,
  lg,
}

/// DocuVerse button primitive matching DESIGN_SYSTEM.md §4.1.
class DocuVerseButton extends StatelessWidget {
  const DocuVerseButton({
    super.key,
    required this.onPressed,
    this.text,
    this.child,
    this.icon,
    this.variant = DocuVerseButtonVariant.primary,
    this.size = DocuVerseButtonSize.md,
    this.loading = false,
    this.disabled = false,
    this.fullWidth = false,
    this.tooltip,
  }) : assert(text != null || child != null || icon != null, 'Must provide text, child, or icon');

  final VoidCallback? onPressed;
  final String? text;
  final Widget? child;
  final Widget? icon;
  final DocuVerseButtonVariant variant;
  final DocuVerseButtonSize size;
  final bool loading;
  final bool disabled;
  final bool fullWidth;
  final String? tooltip;

  double get _height {
    switch (size) {
      case DocuVerseButtonSize.sm:
        return 32.0;
      case DocuVerseButtonSize.md:
        return 36.0;
      case DocuVerseButtonSize.lg:
        return 44.0;
    }
  }

  double get _horizontalPadding {
    switch (size) {
      case DocuVerseButtonSize.sm:
        return 12.0;
      case DocuVerseButtonSize.md:
        return 16.0;
      case DocuVerseButtonSize.lg:
        return 20.0;
    }
  }

  double get _fontSize {
    switch (size) {
      case DocuVerseButtonSize.sm:
        return 12.0;
      case DocuVerseButtonSize.md:
      case DocuVerseButtonSize.lg:
        return 14.0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final isInteractive = !disabled && !loading && onPressed != null;

    Color bg;
    Color fg;
    Border? border;

    switch (variant) {
      case DocuVerseButtonVariant.primary:
        bg = colors.brand;
        fg = colors.brandForeground;
        border = null;
        break;
      case DocuVerseButtonVariant.secondary:
        bg = colors.cardRaised;
        fg = colors.foreground;
        border = Border.all(color: colors.border);
        break;
      case DocuVerseButtonVariant.ghost:
        bg = Colors.transparent;
        fg = colors.foregroundMuted;
        border = null;
        break;
      case DocuVerseButtonVariant.danger:
        bg = colors.danger.withValues(alpha: 0.15);
        fg = colors.danger;
        border = Border.all(color: colors.danger.withValues(alpha: 0.3));
        break;
      case DocuVerseButtonVariant.outline:
        bg = Colors.transparent;
        fg = colors.brand;
        border = Border.all(color: colors.brand.withValues(alpha: 0.4));
        break;
    }

    Widget content;
    if (loading) {
      content = SizedBox(
        width: 16,
        height: 16,
        child: CircularProgressIndicator(
          strokeWidth: 2.0,
          valueColor: AlwaysStoppedAnimation<Color>(fg),
        ),
      );
    } else {
      final List<Widget> rowChildren = [];
      if (icon != null) {
        rowChildren.add(IconTheme(
          data: IconThemeData(size: 16, color: fg),
          child: icon!,
        ));
      }
      if (text != null) {
        if (icon != null) rowChildren.add(const SizedBox(width: 6));
        rowChildren.add(Text(
          text!,
          style: TextStyle(
            fontFamily: DocuVerseTypography.fontBody,
            fontSize: _fontSize,
            fontWeight: FontWeight.w500,
            color: fg,
          ),
        ));
      }
      if (child != null) {
        if (icon != null || text != null) rowChildren.add(const SizedBox(width: 6));
        rowChildren.add(child!);
      }

      content = Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: rowChildren,
      );
    }

    Widget button = Material(
      color: isInteractive ? bg : bg.withValues(alpha: 0.5),
      borderRadius: BorderRadius.circular(colors.buttonRadius),
      child: InkWell(
        onTap: isInteractive ? onPressed : null,
        borderRadius: BorderRadius.circular(colors.buttonRadius),
        child: Container(
          height: _height,
          padding: EdgeInsets.symmetric(horizontal: _horizontalPadding),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(colors.buttonRadius),
            border: border,
          ),
          alignment: Alignment.center,
          child: content,
        ),
      ),
    );

    if (fullWidth) {
      button = SizedBox(width: double.infinity, child: button);
    }

    if (tooltip != null && tooltip!.isNotEmpty) {
      button = Tooltip(
        message: tooltip!,
        child: button,
      );
    }

    return button;
  }
}
