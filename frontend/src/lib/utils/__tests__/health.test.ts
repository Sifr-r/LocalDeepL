import { describe, it, expect } from 'vitest';
import { parseHealthBody, classifyPingError } from '../health';

describe('health utils', () => {
  describe('parseHealthBody', () => {
    it('returns "ok" when the body has status "ok"', () => {
      expect(parseHealthBody({ status: 'ok' })).toBe('ok');
    });

    it('returns "not-ok" when the body has any other status', () => {
      expect(parseHealthBody({ status: 'degraded' })).toBe('not-ok');
      expect(parseHealthBody({ status: '' })).toBe('not-ok');
    });

    it('returns null when the body is null (no response)', () => {
      expect(parseHealthBody(null)).toBeNull();
    });
  });

  describe('classifyPingError', () => {
    it('returns "aborted" for an AbortError DOMException', () => {
      const err = new DOMException('aborted', 'AbortError');
      expect(classifyPingError(err)).toBe('aborted');
    });

    it('returns "down" for any other error', () => {
      expect(classifyPingError(new Error('network'))).toBe('down');
      expect(classifyPingError('string error')).toBe('down');
      expect(classifyPingError(null)).toBe('down');
    });
  });
});
