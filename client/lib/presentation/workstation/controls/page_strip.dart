import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';

/// Thumbnail strip allowing users to quickly preview and switch between pages.
class PageStrip extends ConsumerWidget {
  const PageStrip({
    super.key,
    this.orientation = Axis.horizontal,
  });

  final Axis orientation;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final colors = context.colors;
    final wsState = ref.watch(workstationProvider);
    final notifier = ref.read(workstationProvider.notifier);

    final pageCount = wsState.pageCount;
    final selectedIdx = wsState.selectedPageIndex;

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
        borderRadius: BorderRadius.circular(8),
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
                style: AppTypography.micro(
                  color: colors.textMuted,
                ),
              ),
              Text(
                '${wsState.pages.where((p) => p.bboxes.isNotEmpty).length}/$pageCount scanned',
                style: AppTypography.codeSmall(
                  color: colors.textMuted,
                ).copyWith(fontSize: 10),
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
                final pageResult = index < wsState.pages.length
                    ? wsState.pages[index]
                    : null;
                final boxCount = pageResult?.bboxes.length ?? 0;
                final hasScanned = boxCount > 0;

                return InkWell(
                  onTap: () => notifier.selectPage(index),
                  borderRadius: BorderRadius.circular(6),
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    width: isHorizontal ? 68 : null,
                    padding: const EdgeInsets.all(4),
                    decoration: BoxDecoration(
                      color: isSelected
                          ? colors.brand.withValues(alpha: 0.15)
                          : colors.card,
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
                              border: Border.all(
                                  color: colors.border.withValues(alpha: 0.5)),
                            ),
                            child: Stack(
                              children: [
                                Center(
                                  child: Icon(
                                    Icons.description_outlined,
                                    size: 20,
                                    color: isSelected
                                        ? colors.brand
                                        : colors.textMuted,
                                  ),
                                ),
                                if (hasScanned)
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
                        FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Text(
                            boxCount > 0
                                ? 'P.${index + 1} ($boxCount)'
                                : 'P.${index + 1}',
                            style: AppTypography.codeSmall(
                              color: isSelected
                                  ? colors.brand
                                  : colors.textMuted,
                            ).copyWith(
                              fontSize: 10,
                              fontWeight: isSelected
                                  ? FontWeight.w700
                                  : FontWeight.w500,
                            ),
                          ),
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
