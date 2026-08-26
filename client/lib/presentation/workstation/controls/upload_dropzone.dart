import 'dart:typed_data';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:omniscribe_client/state/document_provider.dart';
import 'package:omniscribe_client/theme/docuverse_colors.dart';
import 'package:omniscribe_client/theme/docuverse_theme.dart';
import 'package:omniscribe_client/theme/docuverse_typography.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_badge.dart';
import 'package:omniscribe_client/presentation/widgets/docuverse_button.dart';

/// Drag & Drop zone supporting desktop_drop and native file_picker
/// Supports PDF, PNG, JPG, WEBP, AVIF with file size validation.
class UploadDropzone extends StatefulWidget {
  const UploadDropzone({
    super.key,
    this.onFileLoaded,
    this.maxBytes = 50 * 1024 * 1024, // 50MB
  });

  final void Function(Uint8List bytes, String filename, int pageCount)?
      onFileLoaded;
  final int maxBytes;

  @override
  State<UploadDropzone> createState() => _UploadDropzoneState();
}

class _UploadDropzoneState extends State<UploadDropzone> {
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

    final docNotifier = DocumentProvider.notifierOf(context);
    docNotifier.loadDocument(
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
    final colors = context.docuVerse;
    final docState = DocumentProvider.of(context);

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
          borderRadius: BorderRadius.circular(colors.cardRadius),
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
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontDisplay,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                  color: colors.foreground,
                ),
              ),
              const SizedBox(height: 8),

              Text(
                'Drag and drop your file here, or browse files on your computer',
                style: TextStyle(
                  fontFamily: DocuVerseTypography.fontBody,
                  fontSize: 13,
                  color: colors.foregroundMuted,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),

              // Format Pills
              Wrap(
                spacing: 8,
                runSpacing: 6,
                alignment: WrapAlignment.center,
                children: const [
                  DocuVerseBadge(
                      text: 'PDF', variant: DocuVerseBadgeVariant.brand),
                  DocuVerseBadge(
                      text: 'PNG', variant: DocuVerseBadgeVariant.neutral),
                  DocuVerseBadge(
                      text: 'JPG', variant: DocuVerseBadgeVariant.neutral),
                  DocuVerseBadge(
                      text: 'WEBP', variant: DocuVerseBadgeVariant.neutral),
                  DocuVerseBadge(
                      text: 'AVIF', variant: DocuVerseBadgeVariant.neutral),
                ],
              ),
              const SizedBox(height: 24),

              // Browse Button
              DocuVerseButton(
                text: 'Browse Files',
                variant: DocuVerseButtonVariant.primary,
                size: DocuVerseButtonSize.lg,
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
                    color: colors.danger.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(colors.radiusInput),
                    border:
                        Border.all(color: colors.danger.withValues(alpha: 0.3)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.error_outline, size: 16, color: colors.danger),
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          _errorMessage!,
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontBody,
                            fontSize: 12,
                            color: colors.danger,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],

              // Current Document Status summary (if already loaded)
              if (docState.hasDocument && docState.filename != null) ...[
                const SizedBox(height: 24),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  decoration: BoxDecoration(
                    color: colors.cardRaised,
                    borderRadius: BorderRadius.circular(colors.radiusInput),
                    border: Border.all(color: colors.border),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle_outline,
                          size: 18, color: colors.success),
                      const SizedBox(width: 8),
                      Text(
                        'Loaded: ${docState.filename}',
                        style: TextStyle(
                          fontFamily: DocuVerseTypography.fontMono,
                          fontSize: 12,
                          color: colors.foreground,
                        ),
                      ),
                      if (docState.loadedBytes != null) ...[
                        const SizedBox(width: 8),
                        Text(
                          '(${_formatSize(docState.loadedBytes!.length)}, ${docState.pageCount} pages)',
                          style: TextStyle(
                            fontFamily: DocuVerseTypography.fontMono,
                            fontSize: 11,
                            color: colors.foregroundMuted,
                          ),
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
