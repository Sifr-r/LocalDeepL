import 'package:flutter/material.dart';

/// DocuVerse Color Tokens for OmniScribe.
///
/// Implements dark and light theme palettes, primary accents (Indigo/Cyan),
/// status indicators, text foregrounds, and confidence score mapping.
class AppColors {
  AppColors._();

  // ---------------------------------------------------------------------------
  // Dark Palette (Default)
  // ---------------------------------------------------------------------------
  static const Color darkBackground = Color(0xFF0B0F19);
  static const Color darkSurface = Color(0xFF111827);
  static const Color darkCard = Color(0xFF1F2937);
  static const Color darkCardRaised = Color(0xFF1E293B);
  static const Color darkMuted = Color(0xFF334155);
  static const Color darkBorder = Color(0xFF374151);
  static const Color darkBorderStrong = Color(0xFF4B5563);
  static const Color darkInputBorder = Color(0xFF374151);
  static const Color darkOverlay = Color(0xCC0B0F19); // 80% opacity

  // Dark Text Foregrounds
  static const Color darkTextPrimary = Color(0xFFF1F5F9);
  static const Color darkTextSecondary = Color(0xFF94A3B8);
  static const Color darkTextMuted = Color(0xFF64748B);

  // ---------------------------------------------------------------------------
  // Light Palette
  // ---------------------------------------------------------------------------
  static const Color lightBackground = Color(0xFFF8FAFC);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightCard = Color(0xFFF1F5F9);
  static const Color lightCardRaised = Color(0xFFE2E8F0);
  static const Color lightMuted = Color(0xFFE2E8F0);
  static const Color lightBorder = Color(0xFFE2E8F0);
  static const Color lightBorderStrong = Color(0xFFCBD5E1);
  static const Color lightInputBorder = Color(0xFFCBD5E1);
  static const Color lightOverlay = Color(0xCCF8FAFC);

  // Light Text Foregrounds
  static const Color lightTextPrimary = Color(0xFF0F172A);
  static const Color lightTextSecondary = Color(0xFF475569);
  static const Color lightTextMuted = Color(0xFF64748B);

  // ---------------------------------------------------------------------------
  // Primary Accents & Brand
  // ---------------------------------------------------------------------------
  static const Color brand = Color(0xFF6366F1); // Indigo
  static const Color brandLight = Color(0xFF4F46E5);
  static const Color brandDark = Color(0xFF818CF8);
  static const Color brandForeground = Color(0xFFFFFFFF);

  static const Color cyan = Color(0xFF06B6D4);
  static const Color cyanLight = Color(0xFF0891B2);
  static const Color magenta = Color(0xFFD946EF);

  // Ambient Glow Tokens
  static const Color glowIndigo = Color(0x336366F1); // 20% opacity
  static const Color glowCyan = Color(0x2606B6D4); // 15% opacity
  static const Color glowMagenta = Color(0x1AD946EF); // 10% opacity

  // ---------------------------------------------------------------------------
  // Status Colors
  // ---------------------------------------------------------------------------
  static const Color success = Color(0xFF10B981); // Emerald
  static const Color successLight = Color(0xFF15803D);
  static const Color warning = Color(0xFFF59E0B); // Amber
  static const Color warningLight = Color(0xFFB45309);
  static const Color error = Color(0xFFEF4444); // Red / Danger
  static const Color errorLight = Color(0xFFBE123C);
  static const Color info = Color(0xFF3B82F6); // Sky Blue
  static const Color infoLight = Color(0xFF0284C7);

  // ---------------------------------------------------------------------------
  // Helper Methods
  // ---------------------------------------------------------------------------

  /// Returns the semantic color for a confidence score (0.0 to 1.0).
  ///
  /// - `score > 0.85`: High confidence ([success])
  /// - `score >= 0.70`: Medium confidence / Review needed ([warning])
  /// - `score < 0.70`: Low confidence / Error risk ([error])
  /// - `score == null`: Unscored / Default ([textMuted])
  static Color getConfidenceColor(double? score, {bool isDark = true}) {
    if (score == null) {
      return isDark ? darkTextMuted : lightTextMuted;
    }
    if (score > 0.85) {
      return isDark ? success : successLight;
    }
    if (score >= 0.70) {
      return isDark ? warning : warningLight;
    }
    return isDark ? error : errorLight;
  }

  /// Convenience accessor to [AppColorScheme] extension from [BuildContext].
  static AppColorScheme of(BuildContext context) {
    final scheme = Theme.of(context).extension<AppColorScheme>();
    return scheme ?? AppColorScheme.dark();
  }
}

/// ThemeExtension providing strongly typed DocuVerse colors to the widget tree.
class AppColorScheme extends ThemeExtension<AppColorScheme> {
  final Color background;
  final Color surface;
  final Color card;
  final Color cardRaised;
  final Color muted;
  final Color border;
  final Color borderStrong;
  final Color inputBorder;
  final Color overlay;

  final Color brand;
  final Color brandForeground;
  final Color brandAccent;
  final Color cyan;
  final Color magenta;

  final Color textPrimary;
  final Color textSecondary;
  final Color textMuted;

  final Color success;
  final Color warning;
  final Color error;
  final Color info;

  final Color glow1;
  final Color glow2;

  const AppColorScheme({
    required this.background,
    required this.surface,
    required this.card,
    required this.cardRaised,
    required this.muted,
    required this.border,
    required this.borderStrong,
    required this.inputBorder,
    required this.overlay,
    required this.brand,
    required this.brandForeground,
    required this.brandAccent,
    required this.cyan,
    required this.magenta,
    required this.textPrimary,
    required this.textSecondary,
    required this.textMuted,
    required this.success,
    required this.warning,
    required this.error,
    required this.info,
    required this.glow1,
    required this.glow2,
  });

  factory AppColorScheme.dark() {
    return const AppColorScheme(
      background: AppColors.darkBackground,
      surface: AppColors.darkSurface,
      card: AppColors.darkCard,
      cardRaised: AppColors.darkCardRaised,
      muted: AppColors.darkMuted,
      border: AppColors.darkBorder,
      borderStrong: AppColors.darkBorderStrong,
      inputBorder: AppColors.darkInputBorder,
      overlay: AppColors.darkOverlay,
      brand: AppColors.brand,
      brandForeground: AppColors.brandForeground,
      brandAccent: AppColors.brandDark,
      cyan: AppColors.cyan,
      magenta: AppColors.magenta,
      textPrimary: AppColors.darkTextPrimary,
      textSecondary: AppColors.darkTextSecondary,
      textMuted: AppColors.darkTextMuted,
      success: AppColors.success,
      warning: AppColors.warning,
      error: AppColors.error,
      info: AppColors.info,
      glow1: AppColors.glowIndigo,
      glow2: AppColors.glowCyan,
    );
  }

  factory AppColorScheme.light() {
    return const AppColorScheme(
      background: AppColors.lightBackground,
      surface: AppColors.lightSurface,
      card: AppColors.lightCard,
      cardRaised: AppColors.lightCardRaised,
      muted: AppColors.lightMuted,
      border: AppColors.lightBorder,
      borderStrong: AppColors.lightBorderStrong,
      inputBorder: AppColors.lightInputBorder,
      overlay: AppColors.lightOverlay,
      brand: AppColors.brandLight,
      brandForeground: AppColors.brandForeground,
      brandAccent: AppColors.brand,
      cyan: AppColors.cyanLight,
      magenta: AppColors.magenta,
      textPrimary: AppColors.lightTextPrimary,
      textSecondary: AppColors.lightTextSecondary,
      textMuted: AppColors.lightTextMuted,
      success: AppColors.successLight,
      warning: AppColors.warningLight,
      error: AppColors.errorLight,
      info: AppColors.infoLight,
      glow1: Color(0x1A6366F1),
      glow2: Color(0x1406B6D4),
    );
  }

  @override
  AppColorScheme copyWith({
    Color? background,
    Color? surface,
    Color? card,
    Color? cardRaised,
    Color? muted,
    Color? border,
    Color? borderStrong,
    Color? inputBorder,
    Color? overlay,
    Color? brand,
    Color? brandForeground,
    Color? brandAccent,
    Color? cyan,
    Color? magenta,
    Color? textPrimary,
    Color? textSecondary,
    Color? textMuted,
    Color? success,
    Color? warning,
    Color? error,
    Color? info,
    Color? glow1,
    Color? glow2,
  }) {
    return AppColorScheme(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      card: card ?? this.card,
      cardRaised: cardRaised ?? this.cardRaised,
      muted: muted ?? this.muted,
      border: border ?? this.border,
      borderStrong: borderStrong ?? this.borderStrong,
      inputBorder: inputBorder ?? this.inputBorder,
      overlay: overlay ?? this.overlay,
      brand: brand ?? this.brand,
      brandForeground: brandForeground ?? this.brandForeground,
      brandAccent: brandAccent ?? this.brandAccent,
      cyan: cyan ?? this.cyan,
      magenta: magenta ?? this.magenta,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textMuted: textMuted ?? this.textMuted,
      success: success ?? this.success,
      warning: warning ?? this.warning,
      error: error ?? this.error,
      info: info ?? this.info,
      glow1: glow1 ?? this.glow1,
      glow2: glow2 ?? this.glow2,
    );
  }

  @override
  AppColorScheme lerp(ThemeExtension<AppColorScheme>? other, double t) {
    if (other is! AppColorScheme) {
      return this;
    }
    return AppColorScheme(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      card: Color.lerp(card, other.card, t)!,
      cardRaised: Color.lerp(cardRaised, other.cardRaised, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      border: Color.lerp(border, other.border, t)!,
      borderStrong: Color.lerp(borderStrong, other.borderStrong, t)!,
      inputBorder: Color.lerp(inputBorder, other.inputBorder, t)!,
      overlay: Color.lerp(overlay, other.overlay, t)!,
      brand: Color.lerp(brand, other.brand, t)!,
      brandForeground: Color.lerp(brandForeground, other.brandForeground, t)!,
      brandAccent: Color.lerp(brandAccent, other.brandAccent, t)!,
      cyan: Color.lerp(cyan, other.cyan, t)!,
      magenta: Color.lerp(magenta, other.magenta, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      error: Color.lerp(error, other.error, t)!,
      info: Color.lerp(info, other.info, t)!,
      glow1: Color.lerp(glow1, other.glow1, t)!,
      glow2: Color.lerp(glow2, other.glow2, t)!,
    );
  }
}

/// Extension for convenient context color lookup.
extension AppColorsExtension on BuildContext {
  AppColorScheme get colors => AppColors.of(this);
}
