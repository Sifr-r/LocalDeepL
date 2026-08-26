import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';
import 'package:omniscribe_client/presentation/common/app_card.dart';
import 'package:omniscribe_client/presentation/common/app_input.dart';
import 'package:omniscribe_client/presentation/common/app_select.dart';
import 'package:omniscribe_client/presentation/common/toast_service.dart';

/// Structured Schema Extraction View.
class ExtractionView extends ConsumerStatefulWidget {
  const ExtractionView({super.key});

  @override
  ConsumerState<ExtractionView> createState() => _ExtractionViewState();
}

class _ExtractionViewState extends ConsumerState<ExtractionView> {
  String _template = 'invoice';
  bool _isExtracting = false;

  final TextEditingController _jsonResultController = TextEditingController(
    text: '''{
  "document_type": "commercial_invoice",
  "invoice_number": "INV-2026-0891",
  "issue_date": "2026-08-24",
  "vendor": {
    "name": "DocuVerse Technologies Inc.",
    "tax_id": "US-88392019"
  },
  "customer": {
    "name": "Acme Global Enterprise",
    "account_ref": "ACM-9921"
  },
  "line_items": [
    {
      "description": "OmniScribe Enterprise Node License",
      "quantity": 10,
      "unit_price": 450.00,
      "amount": 4500.00
    },
    {
      "description": "GPU Cloud Compute Cluster (Hours)",
      "quantity": 100,
      "unit_price": 3.20,
      "amount": 320.00
    }
  ],
  "subtotal": 4820.00,
  "tax": 385.60,
  "total": 5205.60,
  "currency": "USD"
}''',
  );

  @override
  void dispose() {
    _jsonResultController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Schema & Entity Extraction',
                    style:
                        AppTypography.displayMedium(color: colors.textPrimary),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Transform unstructured OCR and document text into strictly validated JSON schemas.',
                    style: AppTypography.bodySmall(color: colors.textSecondary),
                  ),
                ],
              ),
              const Spacer(),
              AppBadge(
                label: 'Pydantic Strict Mode',
                variant: AppBadgeVariant.success,
                size: AppBadgeSize.md,
              ),
            ],
          ),
          const SizedBox(height: 20),

          // Template and Parameters Bar
          AppCard(
            variant: AppCardVariant.raised,
            padding: AppCardPadding.sm,
            child: Row(
              children: [
                Expanded(
                  child: AppSelect<String>(
                    label: 'Target Template',
                    value: _template,
                    items: const [
                      AppSelectItem(
                          value: 'invoice',
                          label: 'Commercial Invoice (Financial)'),
                      AppSelectItem(
                          value: 'resume', label: 'Curriculum Vitae / Resume'),
                      AppSelectItem(
                          value: 'academic',
                          label: 'Academic Paper / Bibliography'),
                      AppSelectItem(
                          value: 'table', label: 'Table Matrix Extraction'),
                      AppSelectItem(
                          value: 'custom', label: 'Custom JSON Schema'),
                    ],
                    onChanged: (v) {
                      if (v != null) setState(() => _template = v);
                    },
                  ),
                ),
                const SizedBox(width: 16),
                Padding(
                  padding: const EdgeInsets.only(top: 20),
                  child: AppButton(
                    text: _isExtracting ? 'Extracting...' : 'Run Extraction',
                    icon: const Icon(Icons.bolt),
                    variant: AppButtonVariant.primary,
                    size: AppButtonSize.md,
                    loading: _isExtracting,
                    onPressed: () {
                      setState(() => _isExtracting = true);
                      Future.delayed(const Duration(milliseconds: 1200), () {
                        if (mounted) {
                          setState(() => _isExtracting = false);
                          ref.read(toastProvider.notifier).success(
                              'Schema extracted: 8 entity groups identified');
                        }
                      });
                    },
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),

          // JSON Schema Result Card
          AppCard(
            title: 'Extracted JSON Output',
            subtitle: 'Validated schema representation',
            headerLeading:
                Icon(Icons.data_object, size: 18, color: colors.brandAccent),
            headerAction: Row(
              children: [
                AppButton(
                  text: 'Validate Schema',
                  variant: AppButtonVariant.ghost,
                  size: AppButtonSize.sm,
                  icon: const Icon(Icons.check_circle_outline, size: 14),
                  onPressed: () {
                    ref
                        .read(toastProvider.notifier)
                        .success('Schema validated successfully: 0 errors');
                  },
                ),
                const SizedBox(width: 6),
                AppButton(
                  text: 'Copy JSON',
                  variant: AppButtonVariant.secondary,
                  size: AppButtonSize.sm,
                  icon: const Icon(Icons.copy, size: 14),
                  onPressed: () {
                    ref
                        .read(toastProvider.notifier)
                        .success('JSON copied to clipboard');
                  },
                ),
              ],
            ),
            child: AppInput(
              controller: _jsonResultController,
              monospace: true,
              maxLines: 20,
              minLines: 14,
            ),
          ),
        ],
      ),
    );
  }
}
