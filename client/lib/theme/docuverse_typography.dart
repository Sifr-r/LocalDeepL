import 'package:flutter/material.dart';

/// DocuVerse Typography matching DESIGN_SYSTEM.md §2.
/// Display: Fraunces / Serif (h1..h3)
/// Body: Sora / Sans (body, strong, caption, micro)
/// Mono: JetBrains Mono / ui-monospace (metrics, IDs, bbox bounds, percentages)
class DocuVerseTypography {
  DocuVerseTypography._();

  static const String fontDisplay = 'Fraunces';
  static const String fontBody = 'Sora';
  static const String fontMono = 'JetBrains Mono';

  static const List<String> displayFontFallbacks = [
    'Fraunces',
    'Georgia',
    'serif',
  ];

  static const List<String> bodyFontFallbacks = [
    'Sora',
    '-apple-system',
    'BlinkMacSystemFont',
    'Segoe UI',
    'Roboto',
    'sans-serif',
  ];

  static const List<String> monoFontFallbacks = [
    'JetBrains Mono',
    'SFMono-Regular',
    'ui-monospace',
    'Consolas',
    'Courier New',
    'monospace',
  ];

  /// H1: 30 / 36, 600 weight, Display font
  static TextStyle h1(Color color) => TextStyle(
        fontFamily: fontDisplay,
        fontFamilyFallback: displayFontFallbacks,
        fontSize: 30,
        height: 36 / 30,
        fontWeight: FontWeight.w600,
        color: color,
        letterSpacing: -0.5,
      );

  /// H2: 24 / 32, 600 weight, Display font
  static TextStyle h2(Color color) => TextStyle(
        fontFamily: fontDisplay,
        fontFamilyFallback: displayFontFallbacks,
        fontSize: 24,
        height: 32 / 24,
        fontWeight: FontWeight.w600,
        color: color,
        letterSpacing: -0.3,
      );

  /// H3: 18 / 28, 600 weight, Display font
  static TextStyle h3(Color color) => TextStyle(
        fontFamily: fontDisplay,
        fontFamilyFallback: displayFontFallbacks,
        fontSize: 18,
        height: 28 / 18,
        fontWeight: FontWeight.w600,
        color: color,
      );

  /// Body: 14 / 20, 400 weight, Body font
  static TextStyle body(Color color) => TextStyle(
        fontFamily: fontBody,
        fontFamilyFallback: bodyFontFallbacks,
        fontSize: 14,
        height: 20 / 14,
        fontWeight: FontWeight.w400,
        color: color,
      );

  /// Strong: 14 / 20, 500 weight, Body font
  static TextStyle strong(Color color) => TextStyle(
        fontFamily: fontBody,
        fontFamilyFallback: bodyFontFallbacks,
        fontSize: 14,
        height: 20 / 14,
        fontWeight: FontWeight.w500,
        color: color,
      );

  /// Caption: 12 / 16, 400 weight, Body font
  static TextStyle caption(Color color) => TextStyle(
        fontFamily: fontBody,
        fontFamilyFallback: bodyFontFallbacks,
        fontSize: 12,
        height: 16 / 12,
        fontWeight: FontWeight.w400,
        color: color,
      );

  /// Micro: 10 / 14, 500 weight, uppercase tracking
  static TextStyle micro(Color color) => TextStyle(
        fontFamily: fontBody,
        fontFamilyFallback: bodyFontFallbacks,
        fontSize: 10,
        height: 14 / 10,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.8,
        color: color,
      );

  /// Mono: 12 / 16, 400 weight, Monospace font
  static TextStyle mono(Color color,
          {double fontSize = 12, FontWeight weight = FontWeight.w400}) =>
      TextStyle(
        fontFamily: fontMono,
        fontFamilyFallback: monoFontFallbacks,
        fontSize: fontSize,
        height: 1.35,
        fontWeight: weight,
        color: color,
      );
}
