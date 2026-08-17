/**
 * Aggregate streamed OCR ``bboxes`` into per-page plain-text and
 * markdown strings. The streaming OCR pipeline emits one
 * ``block_complete`` WebSocket frame per detected text region; the
 * document store's ``pages`` array is never populated when the
 * modern PDF-blob response shape is in use, so the txt / docx
 * export branches must reconstruct the text from bboxes.
 *
 * The aggregation is intentionally a pure function of its input:
 * it sorts bboxes by (page, block), groups them per page, and
 * joins per-page block text with newlines. Pages are separated by
 * a blank line. Empty / whitespace-only block text is dropped so
 * the output reads as continuous prose, not as gaps between
 * blank bboxes.
 *
 * The function is exported from ``utils/`` so the ExportModal
 * can import it and so the test suite can exercise the corner
 * cases (empty bboxes, single page, multi-page with missing
 * blocks) without rendering the Svelte component.
 */

import type { BBoxItem } from '../types/api';

export function aggregateTextFromBboxes(bboxes: BBoxItem[] | undefined | null): string {
  if (!Array.isArray(bboxes) || bboxes.length === 0) return '';
  const sorted = [...bboxes].sort((a, b) => {
    if (a.page !== b.page) return a.page - b.page;
    return a.block - b.block;
  });
  const pageTexts: string[] = [];
  let currentPage = -1;
  let currentLines: string[] = [];
  for (const b of sorted) {
    const text = (b.text ?? '').trim();
    if (!text) continue;
    if (b.page !== currentPage) {
      if (currentLines.length > 0) {
        pageTexts.push(currentLines.join('\n'));
      }
      currentPage = b.page;
      currentLines = [text];
    } else {
      currentLines.push(text);
    }
  }
  if (currentLines.length > 0) {
    pageTexts.push(currentLines.join('\n'));
  }
  return pageTexts.join('\n\n');
}

export function aggregateMarkdownFromBboxes(
  bboxes: BBoxItem[] | undefined | null,
): string {
  if (!Array.isArray(bboxes) || bboxes.length === 0) return '';
  const sorted = [...bboxes].sort((a, b) => {
    if (a.page !== b.page) return a.page - b.page;
    return a.block - b.block;
  });
  const pageChunks: string[] = [];
  let currentPage = -1;
  let currentLines: string[] = [];
  const flush = (): void => {
    if (currentLines.length === 0) return;
    pageChunks.push(`## Page ${currentPage + 1}\n\n${currentLines.join('\n')}`);
  };
  for (const b of sorted) {
    const text = (b.text ?? '').trim();
    if (!text) continue;
    if (b.page !== currentPage) {
      flush();
      currentPage = b.page;
      currentLines = [text];
    } else {
      currentLines.push(text);
    }
  }
  flush();
  return pageChunks.join('\n\n') + '\n';
}
