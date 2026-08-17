import { describe, expect, it } from 'vitest';
import type { BBoxItem } from '../../types/api';
import {
  aggregateMarkdownFromBboxes,
  aggregateTextFromBboxes,
} from '../exportAggregation';

const bbox = (page: number, block: number, text: string, extra: Partial<BBoxItem> = {}): BBoxItem => ({
  block_id: `p${page}_b${block}`,
  page,
  block,
  bbox: [0, 0, 1, 1],
  confidence: 0.95,
  text,
  kind: 'text',
  revised: false,
  ...extra,
});

describe('aggregateTextFromBboxes', () => {
  it('returns empty string for empty / missing bboxes', () => {
    expect(aggregateTextFromBboxes(undefined)).toBe('');
    expect(aggregateTextFromBboxes(null)).toBe('');
    expect(aggregateTextFromBboxes([])).toBe('');
  });

  it('joins a single page with newlines (no blank-line gap)', () => {
    const out = aggregateTextFromBboxes([
      bbox(0, 0, 'line one'),
      bbox(0, 1, 'line two'),
      bbox(0, 2, 'line three'),
    ]);
    expect(out).toBe('line one\nline two\nline three');
  });

  it('separates multiple pages with a blank line', () => {
    const out = aggregateTextFromBboxes([
      bbox(0, 0, 'p1 a'),
      bbox(0, 1, 'p1 b'),
      bbox(1, 0, 'p2 a'),
      bbox(1, 1, 'p2 b'),
    ]);
    expect(out).toBe('p1 a\np1 b\n\np2 a\np2 b');
  });

  it('handles out-of-order bboxes (sorts by page then block)', () => {
    const out = aggregateTextFromBboxes([
      bbox(1, 0, 'p2 a'),
      bbox(0, 1, 'p1 b'),
      bbox(0, 0, 'p1 a'),
      bbox(1, 1, 'p2 b'),
    ]);
    expect(out).toBe('p1 a\np1 b\n\np2 a\np2 b');
  });

  it('skips empty / whitespace-only block text (regression: dense bboxes from low-confidence OCR)', () => {
    const out = aggregateTextFromBboxes([
      bbox(0, 0, 'real text'),
      bbox(0, 1, '   '),
      bbox(0, 2, ''),
      bbox(0, 3, 'more real text'),
    ]);
    expect(out).toBe('real text\nmore real text');
  });

  it('treats empty block text as a skip (matches the OCR low-confidence pass-through)', () => {
    // ``BBoxItem.text`` is typed as a required string; the empty
    // string is the closest stable representation of "no text
    // was detected", and the aggregator must drop it.
    const out = aggregateTextFromBboxes([
      bbox(0, 0, 'kept'),
      bbox(0, 1, ''),
      bbox(0, 2, 'kept again'),
    ]);
    expect(out).toBe('kept\nkept again');
  });

  it('handles non-contiguous pages (page 0, page 2) without leaving page 1 blank', () => {
    const out = aggregateTextFromBboxes([
      bbox(0, 0, 'p1 a'),
      bbox(2, 0, 'p3 a'),
    ]);
    expect(out).toBe('p1 a\n\np3 a');
  });
});

describe('aggregateMarkdownFromBboxes', () => {
  it('returns empty string for empty / missing bboxes', () => {
    expect(aggregateMarkdownFromBboxes(undefined)).toBe('');
    expect(aggregateMarkdownFromBboxes(null)).toBe('');
    expect(aggregateMarkdownFromBboxes([])).toBe('');
  });

  it('prepends ``## Page N`` to each page so the DOCX is navigable', () => {
    const out = aggregateMarkdownFromBboxes([
      bbox(0, 0, 'p1 a'),
      bbox(0, 1, 'p1 b'),
      bbox(1, 0, 'p2 a'),
    ]);
    expect(out).toBe('## Page 1\n\np1 a\np1 b\n\n## Page 2\n\np2 a\n');
  });

  it('handles out-of-order bboxes (sorts by page then block)', () => {
    const out = aggregateMarkdownFromBboxes([
      bbox(1, 0, 'p2 a'),
      bbox(0, 0, 'p1 a'),
    ]);
    expect(out).toBe('## Page 1\n\np1 a\n\n## Page 2\n\np2 a\n');
  });

  it('skips empty block text', () => {
    const out = aggregateMarkdownFromBboxes([
      bbox(0, 0, 'kept'),
      bbox(0, 1, '   '),
      bbox(0, 2, 'kept again'),
    ]);
    expect(out).toBe('## Page 1\n\nkept\nkept again\n');
  });
});
