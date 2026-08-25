import 'package:flutter/material.dart';
import 'docuverse_colors.dart';

/// Theme extension for easy access to DocuVerse design tokens throughout the widget tree.
@immutable
class DocuVerseThemeTokens extends ThemeExtension<DocuVerseThemeTokens> {
  const DocuVerseThemeTokens({
    required this.app,
    required this.background,
    required this.card,
    required this.cardRaised,
    required this.muted,
    required this.overlay,
    required this.foreground,
    required this.foregroundMuted,
    required this.foregroundSubtle,
    required this.border,
    required this.borderStrong,
    required this.input,
    required this.brand,
    required this.brandForeground,
    required this.success,
    required this.warning,
    required this.danger,
    required this.info,
    required this.ring,
    required this.revisedCyan,
    required this.radiusCard,
    required this.radiusInput,
    required this.cardRadius,
    required this.buttonRadius,
    required this.badgeRadius,
  });

  final Color app;
  final Color background;
  final Color card;
  final Color cardRaised;
  final Color muted;
  final Color overlay;
  final Color foreground;
  final Color foregroundMuted;
  final Color foregroundSubtle;
  final Color border;
  final Color borderStrong;
  final Color input;
  final Color brand;
  final Color brandForeground;
  final Color success;
  final Color warning;
  final Color danger;
  final Color info;
  final double radiusCard;
  final double radiusInput;
  final double cardRadius;
  final double buttonRadius;
  final double badgeRadius;

  /// Focus ring color (alias for brand in dark, derived in light).
  final Color ring;

  /// Accent color for "revised" / repaired content.
  final Color revisedCyan;

  static const DocuVerseThemeTokens dark = DocuVerseThemeTokens(
    app: DocuVerseColors.darkApp,
    background: DocuVerseColors.darkBackground,
    card: DocuVerseColors.darkCard,
    cardRaised: DocuVerseColors.darkCardRaised,
    muted: DocuVerseColors.darkMuted,
    overlay: DocuVerseColors.darkOverlay,
    foreground: DocuVerseColors.darkForeground,
    foregroundMuted: DocuVerseColors.darkForegroundMuted,
    foregroundSubtle: DocuVerseColors.darkForegroundSubtle,
    border: DocuVerseColors.darkBorder,
    borderStrong: DocuVerseColors.darkBorderStrong,
    input: DocuVerseColors.darkInput,
    brand: DocuVerseColors.darkBrand,
    brandForeground: DocuVerseColors.darkBrandForeground,
    success: DocuVerseColors.darkSuccess,
    warning: DocuVerseColors.darkWarning,
    danger: DocuVerseColors.darkDanger,
    info: DocuVerseColors.darkInfo,
    ring: DocuVerseColors.darkBrand,
    revisedCyan: DocuVerseColors.darkInfo,
    radiusCard: 8.0,
    radiusInput: 6.0,
    cardRadius: 10.0,
    buttonRadius: 8.0,
    badgeRadius: 999.0,
  );

  static const DocuVerseThemeTokens light = DocuVerseThemeTokens(
    app: DocuVerseColors.lightApp,
    background: DocuVerseColors.lightBackground,
    card: DocuVerseColors.lightCard,
    cardRaised: DocuVerseColors.lightCardRaised,
    muted: DocuVerseColors.lightMuted,
    overlay: DocuVerseColors.lightOverlay,
    foreground: DocuVerseColors.lightForeground,
    foregroundMuted: DocuVerseColors.lightForegroundMuted,
    foregroundSubtle: DocuVerseColors.lightForegroundSubtle,
    border: DocuVerseColors.lightBorder,
    borderStrong: DocuVerseColors.lightBorderStrong,
    input: DocuVerseColors.lightInput,
    brand: DocuVerseColors.lightBrand,
    brandForeground: DocuVerseColors.lightBrandForeground,
    success: DocuVerseColors.lightSuccess,
    warning: DocuVerseColors.lightWarning,
    danger: DocuVerseColors.lightDanger,
    info: DocuVerseColors.lightInfo,
    ring: DocuVerseColors.lightBrand,
    revisedCyan: DocuVerseColors.lightInfo,
    radiusCard: 8.0,
    radiusInput: 6.0,
    cardRadius: 10.0,
    buttonRadius: 8.0,
    badgeRadius: 999.0,
  );

  @override
  DocuVerseThemeTokens copyWith({
    Color? app,
    Color? background,
    Color? card,
    Color? cardRaised,
    Color? muted,
    Color? overlay,
    Color? foreground,
    Color? foregroundMuted,
    Color? foregroundSubtle,
    Color? border,
    Color? borderStrong,
    Color? input,
    Color? brand,
    Color? brandForeground,
    Color? success,
    Color? warning,
    Color? danger,
    Color? info,
    Color? ring,
    Color? revisedCyan,
    double? radiusCard,
    double? radiusInput,
    double? cardRadius,
    double? buttonRadius,
    double? badgeRadius,
  }) {
    return DocuVerseThemeTokens(
      app: app ?? this.app,
      background: background ?? this.background,
      card: card ?? this.card,
      cardRaised: cardRaised ?? this.cardRaised,
      muted: muted ?? this.muted,
      overlay: overlay ?? this.overlay,
      foreground: foreground ?? this.foreground,
      foregroundMuted: foregroundMuted ?? this.foregroundMuted,
      foregroundSubtle: foregroundSubtle ?? this.foregroundSubtle,
      border: border ?? this.border,
      borderStrong: borderStrong ?? this.borderStrong,
      input: input ?? this.input,
      brand: brand ?? this.brand,
      brandForeground: brandForeground ?? this.brandForeground,
      success: success ?? this.success,
      warning: warning ?? this.warning,
      danger: danger ?? this.danger,
      info: info ?? this.info,
      ring: ring ?? this.ring,
      revisedCyan: revisedCyan ?? this.revisedCyan,
      radiusCard: radiusCard ?? this.radiusCard,
      radiusInput: radiusInput ?? this.radiusInput,
      cardRadius: cardRadius ?? this.cardRadius,
      buttonRadius: buttonRadius ?? this.buttonRadius,
      badgeRadius: badgeRadius ?? this.badgeRadius,
    );
  }

  @override
  DocuVerseThemeTokens lerp(ThemeExtension<DocuVerseThemeTokens>? other, double t) {
    if (other is! DocuVerseThemeTokens) return this;
    return DocuVerseThemeTokens(
      app: Color.lerp(app, other.app, t) ?? app,
      background: Color.lerp(background, other.background, t) ?? background,
      card: Color.lerp(card, other.card, t) ?? card,
      cardRaised: Color.lerp(cardRaised, other.cardRaised, t) ?? cardRaised,
      muted: Color.lerp(muted, other.muted, t) ?? muted,
      overlay: Color.lerp(overlay, other.overlay, t) ?? overlay,
      foreground: Color.lerp(foreground, other.foreground, t) ?? foreground,
      foregroundMuted: Color.lerp(foregroundMuted, other.foregroundMuted, t) ?? foregroundMuted,
      foregroundSubtle: Color.lerp(foregroundSubtle, other.foregroundSubtle, t) ?? foregroundSubtle,
      border: Color.lerp(border, other.border, t) ?? border,
      borderStrong: Color.lerp(borderStrong, other.borderStrong, t) ?? borderStrong,
      input: Color.lerp(input, other.input, t) ?? input,
      brand: Color.lerp(brand, other.brand, t) ?? brand,
      brandForeground: Color.lerp(brandForeground, other.brandForeground, t) ?? brandForeground,
      success: Color.lerp(success, other.success, t) ?? success,
      warning: Color.lerp(warning, other.warning, t) ?? warning,
      danger: Color.lerp(danger, other.danger, t) ?? danger,
      info: Color.lerp(info, other.info, t) ?? info,
      ring: Color.lerp(ring, other.ring, t) ?? ring,
      revisedCyan: Color.lerp(revisedCyan, other.revisedCyan, t) ?? revisedCyan,
      radiusCard: (radiusCard + (other.radiusCard - radiusCard) * t),
      radiusInput: (radiusInput + (other.radiusInput - radiusInput) * t),
      cardRadius: (cardRadius + (other.cardRadius - cardRadius) * t),
      buttonRadius: (buttonRadius + (other.buttonRadius - buttonRadius) * t),
      badgeRadius: (badgeRadius + (other.badgeRadius - badgeRadius) * t),
    );
  }
}

/// Helper extension on [BuildContext] to quickly retrieve [DocuVerseThemeTokens].
extension DocuVerseThemeContext on BuildContext {
  DocuVerseThemeTokens get docuVerse =>
      Theme.of(this).extension<DocuVerseThemeTokens>() ?? DocuVerseThemeTokens.dark;
}

/// Main DocuVerse ThemeData builder.
class DocuVerseTheme {
  static ThemeData get darkTheme {
    const tokens = DocuVerseThemeTokens.dark;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: tokens.app,
      colorScheme: ColorScheme.dark(
        primary: tokens.brand,
        onPrimary: tokens.brandForeground,
        surface: tokens.card,
        onSurface: tokens.foreground,
        error: tokens.danger,
        onError: Colors.white,
      ),
      cardTheme: CardThemeData(
        color: tokens.card,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(tokens.radiusCard),
          side: BorderSide(color: tokens.border),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: tokens.border,
        thickness: 1,
        space: 1,
      ),
      extensions: const [tokens],
    );
  }

  static ThemeData get lightTheme {
    const tokens = DocuVerseThemeTokens.light;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: tokens.app,
      colorScheme: ColorScheme.light(
        primary: tokens.brand,
        onPrimary: tokens.brandForeground,
        surface: tokens.card,
        onSurface: tokens.foreground,
        error: tokens.danger,
        onError: Colors.white,
      ),
      cardTheme: CardThemeData(
        color: tokens.card,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(tokens.radiusCard),
          side: BorderSide(color: tokens.border),
        ),
      ),
      dividerTheme: DividerThemeData(
        color: tokens.border,
        thickness: 1,
        space: 1,
      ),
      extensions: const [tokens],
    );
  }
}
