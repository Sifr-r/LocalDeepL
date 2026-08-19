/**
 * Download utility functions.
 *
 * Provides safe filename sanitization and browser-resilient blob / URL
 * downloads. Attaches temporary anchor elements to `document.body` before
 * triggering click and delays `URL.revokeObjectURL` to prevent aborted
 * 0-byte downloads in strict browser environments.
 */

/**
 * Sanitize a filename to strip path traversal sequences and invalid characters.
 */
export function sanitizeFilename(filename: string, fallback = 'download'): string {
  if (!filename || typeof filename !== 'string') return fallback;
  // Replace path separators and traversal tokens
  let cleaned = filename
    .replace(/[/\\]+/g, '_')
    .replace(/\.\.+/g, '_')
    /* eslint-disable-next-line no-control-regex */
    .replace(/[\x00-\x1f\x7f<>:"|?*]/g, '_')
    .trim();
  // Strip leading dots or underscores that might hide files or cause issues
  cleaned = cleaned.replace(/^[._]+/, '');
  return cleaned.length > 0 ? cleaned : fallback;
}

/**
 * Trigger a browser download for a Blob with delayed URL revocation.
 */
export function downloadBlob(blob: Blob, filename: string, revokeDelay = 1000): void {
  const safeName = sanitizeFilename(filename);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = safeName;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    if (a.parentNode) {
      a.parentNode.removeChild(a);
    }
    URL.revokeObjectURL(url);
  }, revokeDelay);
}

/**
 * Trigger a browser download for an existing URL with delayed cleanup.
 */
export function downloadUrl(url: string, filename: string, cleanupDelay = 1000): void {
  const safeName = sanitizeFilename(filename);
  const a = document.createElement('a');
  a.href = url;
  a.download = safeName;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    if (a.parentNode) {
      a.parentNode.removeChild(a);
    }
  }, cleanupDelay);
}
