import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { sanitizeFilename, downloadBlob, downloadUrl } from '../download';

describe('download utils', () => {
  describe('sanitizeFilename', () => {
    it('returns fallback for empty or non-string input', () => {
      expect(sanitizeFilename('')).toBe('download');
      // @ts-expect-error testing invalid type
      expect(sanitizeFilename(null)).toBe('download');
    });

    it('strips path traversal tokens and directory separators', () => {
      expect(sanitizeFilename('../../../etc/passwd')).toBe('etc_passwd');
      expect(sanitizeFilename('..\\..\\windows\\system32.dll')).toBe('windows_system32.dll');
      expect(sanitizeFilename('/path/to/my_file.pdf')).toBe('path_to_my_file.pdf');
    });

    it('replaces dangerous filesystem characters', () => {
      expect(sanitizeFilename('report:final*v1?.txt')).toBe('report_final_v1_.txt');
      expect(sanitizeFilename('<test>|"file".doc')).toBe('test___file_.doc');
    });

    it('strips leading dots and underscores', () => {
      expect(sanitizeFilename('...hidden_file.txt')).toBe('hidden_file.txt');
    });
  });

  describe('downloadBlob and downloadUrl', () => {
    beforeEach(() => {
      vi.useFakeTimers();
      document.body.innerHTML = '';
    });

    afterEach(() => {
      vi.useRealTimers();
      document.body.innerHTML = '';
    });

    it('downloadBlob attaches <a> to document.body, clicks it, and delays URL revocation', () => {
      const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
      const createSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-url');
      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

      const blob = new Blob(['sample text'], { type: 'text/plain' });
      downloadBlob(blob, '../../../my_export.txt');

      expect(createSpy).toHaveBeenCalledWith(blob);
      expect(clickSpy).toHaveBeenCalled();

      // Revoke shouldn't have been called immediately
      expect(revokeSpy).not.toHaveBeenCalled();

      // Fast-forward timer by 1000ms
      vi.advanceTimersByTime(1000);

      expect(revokeSpy).toHaveBeenCalledWith('blob:test-url');
    });

    it('downloadUrl attaches <a> to document.body, clicks it, and cleans up after delay', () => {
      const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

      downloadUrl('https://example.com/file.pdf', 'safe_name.pdf');
      expect(clickSpy).toHaveBeenCalled();

      vi.advanceTimersByTime(1000);
      expect(document.body.querySelectorAll('a').length).toBe(0);
    });
  });
});
