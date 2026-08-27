import 'dart:typed_data';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:omniscribe_client/core/theme/app_colors.dart';
import 'package:omniscribe_client/core/theme/app_typography.dart';
import 'package:omniscribe_client/data/providers/workstation_notifier.dart';
import 'package:omniscribe_client/presentation/common/app_badge.dart';
import 'package:omniscribe_client/presentation/common/app_button.dart';

/// Drag & Drop zone supporting desktop_drop and native file_picker
/// Supports PDF, PNG, JPG, WEBP, AVIF with file size validation.
class UploadDropzone extends ConsumerStatefulWidget {
  const UploadDropzone({
    super.key,
    this.onFileLoaded,
    this.maxBytes = 50 * 1024 * 1024, // 50MB
  });

  final void Function(Uint8List bytes, String filename, int pageCount)?
      onFileLoaded;
  final int maxBytes;

  @override
  ConsumerState<UploadDropzone> createState() => _UploadDropzoneState();
}

class _UploadDropzoneState extends ConsumerState<UploadDropzone> {
  bool _isDragging = false;
  bool _isLoading = false;
  String? _errorMessage;

  static const List<String> supportedExtensions = [
    'pdf',
    'png',
    'jpg',
    'jpeg',
    'webp',
    'avif',
  ];

  Future<void> _pickFile() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final result = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: supportedExtensions,
        withData: true,
      );

      if (result != null && result.files.isNotEmpty) {
        final file = result.files.first;
        final bytes = file.bytes;
        final name = file.name;

        if (bytes != null) {
          _processFile(bytes, name, file.path);
        } else {
          setState(() {
            _errorMessage = 'Could not read file data';
          });
        }
      }
    } catch (err) {
      setState(() {
        _errorMessage = 'Failed to pick file: $err';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  void _processFile(Uint8List bytes, String filename, String? filePath) {
    if (bytes.length > widget.maxBytes) {
      final maxMb = (widget.maxBytes / (1024 * 1024)).round();
      setState(() {
        _errorMessage = 'File exceeds maximum upload size of ${maxMb}MB';
      });
      return;
    }

    final ext = filename.split('.').last.toLowerCase();
    if (!supportedExtensions.contains(ext)) {
      setState(() {
        _errorMessage =
            'Unsupported format .$ext. Please upload PDF, PNG, JPG, WEBP, or AVIF';
      });
      return;
    }

    // Estimate page count (1 for images, estimate from bytes for PDF)
    int estimatedPages = 1;
    if (ext == 'pdf') {
      estimatedPages = _estimatePdfPages(bytes);
    }

    final notifier = ref.read(workstationProvider.notifier);
    notifier.loadDocument(
      bytes,
      filename,
      pageCount: estimatedPages,
      filePath: filePath,
    );

    widget.onFileLoaded?.call(bytes, filename, estimatedPages);
  }

  int _estimatePdfPages(Uint8List bytes) {
    // Quick heuristic scan for /Type /Page in PDF binary
    try {
      final content = String.fromCharCodes(bytes);
      final pageMatches = RegExp(r'/Type\s*/Page\b').allMatches(content);
      final count = pageMatches.length;
      return count > 0 ? count : 1;
    } catch (_) {
      return 1;
    }
  }

  String _formatSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(2)} MB';
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final wsState = ref.watch(workstationProvider);

    return DropTarget(
      onDragEntered: (_) => setState(() => _isDragging = true),
      onDragExited: (_) => setState(() => _isDragging = false),
      onDragDone: (details) async {
        setState(() => _isDragging = false);
        if (details.files.isNotEmpty) {
          final xfile = details.files.first;
          final bytes = await xfile.readAsBytes();
          _processFile(bytes, xfile.name, xfile.path);
        }
      },
      child: Container(
        decoration: BoxDecoration(
          color:
              _isDragging ? colors.brand.withValues(alpha: 0.12) : colors.card,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: _isDragging ? colors.brand : colors.borderStrong,
            width: _isDragging ? 2.0 : 1.2,
          ),
        ),
        padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 48),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Icon Circle with Ambient Glow
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: colors.brand.withValues(alpha: 0.15),
                  border: Border.all(
                    color: colors.brand.withValues(alpha: 0.35),
                    width: 1.5,
                  ),
                ),
                child: Icon(
                  _isDragging
                      ? Icons.file_download_outlined
                      : Icons.cloud_upload_outlined,
                  size: 32,
                  color: colors.brand,
                ),
              ),
              const SizedBox(height: 20),

              // Title & Call to Action
              Text(
                _isDragging
                    ? 'Drop file to load'
                    : 'Upload document for OCR processing',
                style: AppTypography.titleMedium(
                  color: colors.textPrimary,
                ),
              ),
              const SizedBox(height: 8),

              Text(
                'Drag and drop your file here, or browse files on your computer',
                style: AppTypography.bodySmall(
                  color: colors.textMuted,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),

              // Format Pills
              const Wrap(
                spacing: 8,
                runSpacing: 6,
                alignment: WrapAlignment.center,
                children: [
                  AppBadge(
                      label: 'PDF', variant: AppBadgeVariant.brand),
                  AppBadge(
                      label: 'PNG', variant: AppBadgeVariant.neutral),
                  AppBadge(
                      label: 'JPG', variant: AppBadgeVariant.neutral),
                  AppBadge(
                      label: 'WEBP', variant: AppBadgeVariant.neutral),
                  AppBadge(
                      label: 'AVIF', variant: AppBadgeVariant.neutral),
                ],
              ),
              const SizedBox(height: 24),

              // Browse Button
              AppButton(
                text: 'Browse Files',
                variant: AppButtonVariant.primary,
                size: AppButtonSize.lg,
                icon: const Icon(Icons.folder_open_rounded, size: 16),
                loading: _isLoading,
                onPressed: _pickFile,
              ),

              // Error banner if any
              if (_errorMessage != null) ...[
                const SizedBox(height: 16),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: colors.error.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(6),
                    border:
                        Border.all(color: colors.error.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.error_outline, size: 16, color: colors.error),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          _errorMessage!,
                          style: AppTypography.bodySmall(
                            color: colors.error,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Current Document Status summary (if already loaded)
              if (wsState.hasDocument && wsState.filename != null) ...[
                const SizedBox(height: 24),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: colors.cardRaised,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: colors.border),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle_outline,
                          size: 18, color: colors.success),
                      const SizedBox(width: 8),
                      Text(
                        'Loaded: ${wsState.filename}',
                        style: AppTypography.codeSmall(
                          color: colors.textPrimary,
                        ),
                      ),
                      if (wsState.loadedBytes != null) ...[
                        const SizedBox(width: 8),
                        Text(
                          '(${_formatSize(wsState.loadedBytes!.length)}, ${wsState.pageCount} pages)',
                          style: AppTypography.codeSmall(
                            color: colors.textMuted,
                          ).copyWith(fontSize: 11),
                        ),
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
