import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// DocuVerse Slider with label, value indicator, min/max bounds.
class DocuVerseSlider extends StatelessWidget {
  const DocuVerseSlider({
    super.key,
    required this.label,
    required this.value,
    required this.min,
    required this.max,
    this.divisions,
    this.valueLabel,
    required this.onChanged,
    this.helperText,
  });

  final String label;
  final double value;
  final double min;
  final double max;
  final int? divisions;
  final String? valueLabel;
  final ValueChanged<double> onChanged;
  final String? helperText;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontBody,
                fontSize: 12,
                fontWeight: FontWeight.w500,
                color: colors.foregroundMuted,
              ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                color: colors.muted.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: colors.border),
              ),
              child: Text(
                valueLabel ?? value.toStringAsFixed(1),
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontMono,
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: colors.brand,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Slider(
          value: value.clamp(min, max),
          min: min,
          max: max,
          divisions: divisions,
          onChanged: onChanged,
        ),
        if (helperText != null) ...[
          Padding(
            padding: const EdgeInsets.only(left: 4.0),
            child: Text(
              helperText!,
              style: TextStyle(
                fontFamily: DocuVerseTypography.fontBody,
                fontSize: 11,
                color: colors.foregroundSubtle,
              ),
            ),
          ),
        ],
      ],
    );
  }
}
