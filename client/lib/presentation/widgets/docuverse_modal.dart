import 'package:flutter/material.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';

class DocuVerseModal extends StatelessWidget {
  const DocuVerseModal({
    super.key,
    required this.title,
    this.description,
    required this.child,
    this.actions,
    this.maxWidth = 600,
    this.onClose,
  });

  final String title;
  final String? description;
  final Widget child;
  final List<Widget>? actions;
  final double maxWidth;
  final VoidCallback? onClose;

  static Future<T?> show<T>({
    required BuildContext context,
    required String title,
    String? description,
    required Widget child,
    List<Widget>? actions,
    double maxWidth = 600,
  }) {
    return showDialog<T>(
      context: context,
      barrierColor: context.docuVerse.overlay,
      builder: (dialogContext) => DocuVerseModal(
        title: title,
        description: description,
        actions: actions,
        maxWidth: maxWidth,
        onClose: () => Navigator.of(dialogContext).pop(),
        child: child,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.docuVerse;

    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: maxWidth),
        child: Container(
          decoration: BoxDecoration(
            color: tokens.card,
            borderRadius: BorderRadius.circular(tokens.radiusCard + 4),
            border: Border.all(color: tokens.borderStrong, width: 1),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.35),
                blurRadius: 24,
                offset: const Offset(0, 12),
              ),
            ],
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.fromLTRB(20, 18, 16, 14),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            title,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: tokens.foreground,
                            ),
                          ),
                          if (description != null) ...[
                            const SizedBox(height: 3),
                            Text(
                              description!,
                              style: TextStyle(
                                fontSize: 12,
                                color: tokens.foregroundMuted,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.close,
                          size: 18, color: tokens.foregroundMuted),
                      splashRadius: 18,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      onPressed: onClose ?? () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
              ),
              Divider(color: tokens.border, height: 1),
              // Body
              Flexible(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(20),
                  child: child,
                ),
              ),
              // Footer
              if (actions != null && actions!.isNotEmpty) ...[
                Divider(color: tokens.border, height: 1),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      for (int i = 0; i < actions!.length; i++) ...[
                        if (i > 0) const SizedBox(width: 8),
                        actions![i],
                      ],
                    ],
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
