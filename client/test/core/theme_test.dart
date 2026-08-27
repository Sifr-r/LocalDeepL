import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_theme.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  GoogleFonts.config.allowRuntimeFetching = false;

  group('AppColors & Confidence Helper', () {
    test('Dark theme tokens match DocuVerse specifications', () {
      expect(AppColors.darkBackground, const Color(0xFF0B0F19));
      expect(AppColors.darkSurface, const Color(0xFF111827));
      expect(AppColors.darkCard, const Color(0xFF1F2937));
      expect(AppColors.darkBorder, const Color(0xFF374151));
      expect(AppColors.brand, const Color(0xFF6366F1));
    });

    test('Light theme tokens match DocuVerse specifications', () {
      expect(AppColors.lightBackground, const Color(0xFFF8FAFC));
      expect(AppColors.lightSurface, const Color(0xFFFFFFFF));
      expect(AppColors.lightCard, const Color(0xFFF1F5F9));
      expect(AppColors.lightBorder, const Color(0xFFE2E8F0));
    });

    test('getConfidenceColor accurately maps scores', () {
      // > 0.85 -> Success
      expect(
          AppColors.getConfidenceColor(0.95, isDark: true), AppColors.success);
      expect(AppColors.getConfidenceColor(0.86, isDark: false),
          AppColors.successLight);

      // 0.70 - 0.85 -> Warning
      expect(
          AppColors.getConfidenceColor(0.85, isDark: true), AppColors.warning);
      expect(
          AppColors.getConfidenceColor(0.70, isDark: true), AppColors.warning);
      expect(AppColors.getConfidenceColor(0.75, isDark: false),
          AppColors.warningLight);

      // < 0.70 -> Error
      expect(AppColors.getConfidenceColor(0.69, isDark: true), AppColors.error);
      expect(AppColors.getConfidenceColor(0.20, isDark: false),
          AppColors.errorLight);

      // null -> Muted
      expect(AppColors.getConfidenceColor(null, isDark: true),
          AppColors.darkTextMuted);
      expect(AppColors.getConfidenceColor(null, isDark: false),
          AppColors.lightTextMuted);
    });

    test('AppColorScheme provides valid dark and light schemes', () {
      final dark = AppColorScheme.dark();
      final light = AppColorScheme.light();

      expect(dark.background, AppColors.darkBackground);
      expect(light.background, AppColors.lightBackground);
      expect(dark.brand, AppColors.brand);
      expect(light.brand, AppColors.brandLight);
    });
  });

  group('AppTheme & Typography', () {
    test('AppTheme generates valid ThemeData for dark and light mode', () {
      final darkTheme = AppTheme.darkTheme;
      final lightTheme = AppTheme.lightTheme;

      expect(darkTheme.brightness, Brightness.dark);
      expect(lightTheme.brightness, Brightness.light);
      expect(darkTheme.scaffoldBackgroundColor, AppColors.darkBackground);
      expect(lightTheme.scaffoldBackgroundColor, AppColors.lightBackground);

      expect(darkTheme.extension<AppColorScheme>(), isNotNull);
      expect(lightTheme.extension<AppColorScheme>(), isNotNull);
    });

    test('Typography styles define expected sizes and weights', () {
      final h1 = AppTypography.displayLarge();
      final h2 = AppTypography.displayMedium();
      final body = AppTypography.bodyMedium();
      final micro = AppTypography.micro();
      final code = AppTypography.code();

      expect(h1.fontSize, 30);
      expect(h1.fontWeight, FontWeight.w600);
      expect(h2.fontSize, 24);
      expect(body.fontSize, 14);
      expect(micro.fontSize, 10);
      expect(code.fontSize, 13);
    });
  });
}
