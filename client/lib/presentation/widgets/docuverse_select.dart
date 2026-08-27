import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

class DocuVerseSelectItem<T> {
  const DocuVerseSelectItem({
    required this.value,
    required this.label,
    this.subtitle,
  });

  final T value;
  final String label;
  final String? subtitle;
}

/// DocuVerse Select dropdown matching DESIGN_SYSTEM.md §4.3.
class DocuVerseSelect<T> extends StatelessWidget {
  const DocuVerseSelect({
    super.key,
    this.label,
    this.hint,
    this.helperText,
    required this.items,
    required this.value,
    required this.onChanged,
  });

  final String? label;
  final String? hint;
  final String? helperText;
  final List<DocuVerseSelectItem<T>> items;
  final T value;
  final ValueChanged<T?> onChanged;

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
        DropdownButtonFormField<T>(
          isExpanded: true,
          isDense: true,
          initialValue: value,
          itemHeight: null,
          onChanged: onChanged,
          selectedItemBuilder: (BuildContext context) {
            return items.map((item) {
              return Align(
                alignment: Alignment.centerLeft,
                child: Text(
                  item.label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontFamily: DocuVerseTypography.fontBody,
                    fontSize: 13,
                    color: colors.foreground,
                  ),
                ),
              );
            }).toList();
          },
          items: items.map((item) {
            return DropdownMenuItem<T>(
              value: item.value,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    item.label,
                    style: TextStyle(
                      fontFamily: DocuVerseTypography.fontBody,
                      fontSize: 14,
                      color: colors.foreground,
                    ),
                  ),
                  if (item.subtitle != null) ...[
                    Text(
                      item.subtitle!,
                      style: TextStyle(
                        fontFamily: DocuVerseTypography.fontBody,
                        fontSize: 11,
                        color: colors.foregroundMuted,
                      ),
                    ),
                  ],
                ],
              ),
            );
          }).toList(),
          dropdownColor: colors.cardRaised,
          icon: Icon(
            Icons.keyboard_arrow_down_rounded,
            size: 18,
            color: colors.foregroundMuted,
          ),
          decoration: InputDecoration(
            hintText: hint,
            helperText: helperText,
            helperStyle: TextStyle(
              fontFamily: DocuVerseTypography.fontBody,
              fontSize: 11,
              color: colors.foregroundSubtle,
            ),
            contentPadding:
                const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
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
          ),
        ),
      ],
    );
  }
}
