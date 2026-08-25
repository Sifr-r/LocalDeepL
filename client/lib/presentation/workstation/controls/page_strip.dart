import 'package:flutter/material.dart';
import 'package:omniscribe_client/models/document_view_model.dart';
import 'package:omniscribe_client/state/document_provider.dart';
import 'package:omniscribe_client/state/progress_provider.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';

/// Thumbnail strip allowing users to quickly preview and switch between pages.
class PageStrip extends StatelessWidget {
  const PageStrip({
    super.key,
    this.orientation = Axis.horizontal,
  });

  final Axis orientation;

  @override
  Widget build(BuildContext context) {
    final colors = context.docuVerse;
    final docState = DocumentProvider.of(context);
    final docNotifier = DocumentProvider.notifierOf(context);
    final progressState = ProgressProvider.of(context);

    final pageCount = docState.pageCount;
    final selectedIdx = docState.selectedPageIndex;
    final completedPages = progressState.completedPages;

    if (pageCount <= 1) {
      return const SizedBox.shrink();
    }

    final isHorizontal = orientation == Axis.horizontal;

    return Container(
      height: isHorizontal ? 108 : null,
      width: isHorizontal ? null : 120,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colors.cardRaised,
        borderRadius: BorderRadius.circular(colors.cardRadius),
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'PAGES ($pageCount)',
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontBody,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.6,
                  color: colors.foregroundMuted,
                ),
              ),
              Text(
                '${completedPages.length}/$pageCount processed',
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontMono,
                  fontSize: 10,
                  color: colors.foregroundSubtle,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Expanded(
            child: ListView.separated(
              scrollDirection: orientation,
              itemCount: pageCount,
              separatorBuilder: (_, __) => SizedBox(
                width: isHorizontal ? 8 : 0,
                height: isHorizontal ? 0 : 8,
              ),
              itemBuilder: (context, index) {
                final isSelected = index == selectedIdx;
                final isCompleted = completedPages.contains(index);
                final pageResult = index < docState.pages.length ? docState.pages[index] : null;
                final boxCount = pageResult?.bboxes.length ?? 0;

                return InkWell(
                  onTap: () => docNotifier.selectPage(index),
                  borderRadius: BorderRadius.circular(6),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    width: isHorizontal ? 68 : null,
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: isSelected ? colors.brand.withValues(alpha: 0.15) : colors.card,
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(
                        color: isSelected ? colors.brand : colors.border,
                        width: isSelected ? 1.8 : 1.0,
                      ),
                    ),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        // Page Mini Card Preview
                        Expanded(
                          child: Container(
                            decoration: BoxDecoration(
                              color: colors.cardRaised,
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(color: colors.border.withValues(alpha: 0.5)),
                            ),
                            child: Stack(
                              children: [
                                Center(
                                  child: Icon(
                                    Icons.description_outlined,
                                    size: 20,
                                    color: isSelected ? colors.brand : colors.foregroundSubtle,
                                  ),
                                ),
                                if (isCompleted)
                                  Positioned(
                                    top: 2,
                                    right: 2,
                                    child: Container(
                                      padding: const EdgeInsets.all(2),
                                      decoration: BoxDecoration(
                                        color: colors.success,
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Icon(
                                        Icons.check,
                                        size: 8,
                                        color: Colors.white,
                                      ),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ),
                        const SizedBox(height: 4),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Text(
                              'P.${index + 1}',
                              style: TextStyle(
                                fontFamily: DocuVerseTypography.fontMono,
                                fontSize: 10,
                                fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                                color: isSelected ? colors.brand : colors.foregroundMuted,
                              ),
                            ),
                            if (boxCount > 0) ...[
                              const SizedBox(width: 3),
                              Text(
                                '($boxCount)',
                                style: TextStyle(
                                  fontFamily: DocuVerseTypography.fontMono,
                                  fontSize: 8,
                                  color: colors.foregroundSubtle,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
