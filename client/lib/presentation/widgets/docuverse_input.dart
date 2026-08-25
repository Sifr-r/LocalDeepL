import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// DocuVerse Input field with label, hint, error, and prefix/suffix widgets.
class DocuVerseInput extends StatelessWidget {
  const DocuVerseInput({
    super.key,
    this.label,
    this.hint,
    this.placeholder,
    this.helperText,
    this.errorText,
    this.controller,
    this.initialValue,
    this.onChanged,
    this.onSubmitted,
    this.prefixIcon,
    this.suffixIcon,
    this.readOnly = false,
    this.obscureText = false,
    this.isPassword = false,
    this.isMono = false,
    this.maxLines = 1,
    this.minLines,
    this.keyboardType,
    this.textInputAction,
  });

  final String? label;
  final String? hint;
  final String? placeholder;
  final String? helperText;
  final String? errorText;
  final TextEditingController? controller;
  final String? initialValue;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final Widget? prefixIcon;
  final Widget? suffixIcon;
  final bool readOnly;
  final bool obscureText;
  final bool isPassword;
  final bool isMono;
  final int maxLines;
  final int? minLines;
  final TextInputType? keyboardType;
  final TextInputAction? textInputAction;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (label != null) ...[
          Text(
            label!,
            style: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 12,
              fontWeight: FontWeight.w500,
              color: colors.foregroundMuted,
            ),
          ),
          const SizedBox(height: 6),
        ],
        TextFormField(
          controller: controller,
          initialValue: controller == null ? initialValue : null,
          onChanged: onChanged,
          onFieldSubmitted: onSubmitted,
          readOnly: readOnly,
          obscureText: obscureText,
          maxLines: maxLines,
          minLines: minLines,
          keyboardType: keyboardType,
          textInputAction: textInputAction,
          style: TextStyle(
            fontFamily: DocuVerseTypography.fontBody,
            fontSize: 14,
            color: colors.foreground,
          ),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 14,
              color: colors.foregroundSubtle,
            ),
            helperText: helperText,
            helperStyle: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 11,
              color: colors.foregroundSubtle,
            ),
            errorText: errorText,
            errorStyle: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 11,
              color: colors.danger,
            ),
            prefixIcon: prefixIcon != null
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: IconTheme(
                      data: IconThemeData(size: 16, color: colors.foregroundMuted),
                      child: prefixIcon!,
                    ),
                  )
                : null,
            prefixIconConstraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            suffixIcon: suffixIcon != null
                ? Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: IconTheme(
                      data: IconThemeData(size: 16, color: colors.foregroundMuted),
                      child: suffixIcon!,
                    ),
                  )
                : null,
            suffixIconConstraints: const BoxConstraints(minWidth: 36, minHeight: 36),
            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            filled: true,
            fillColor: colors.card,
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(colors.radiusInput),
              borderSide: BorderSide(color: colors.input),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(colors.radiusInput),
              borderSide: BorderSide(color: colors.input),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(colors.radiusInput),
              borderSide: BorderSide(color: colors.ring, width: 1.5),
            ),
            errorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(colors.radiusInput),
              borderSide: BorderSide(color: colors.danger),
            ),
          ),
        ),
      ],
    );
  }
}
