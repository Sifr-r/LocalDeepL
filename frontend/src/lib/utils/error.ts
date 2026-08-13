/**
 * Utility functions for API error handling and humanization.
 */

interface ValidationErrorDetail {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

/**
 * Converts any caught API or runtime error into a clean, human-readable error message string.
 */
export function humanizeApiError(err: unknown): string {
  if (!err) {
    return 'An unknown error occurred.';
  }

  if (typeof err === 'string') {
    return err.trim() || 'An error occurred.';
  }

  if (err instanceof Error) {
    return err.message || 'An unexpected error occurred.';
  }

  if (typeof err === 'object') {
    const record = err as Record<string, unknown>;

    // Handle FastAPI / Pydantic HTTP 422 error details
    if (record.detail !== undefined) {
      if (typeof record.detail === 'string') {
        return record.detail;
      }
      if (Array.isArray(record.detail)) {
        const messages = (record.detail as ValidationErrorDetail[])
          .map((item) => {
            if (typeof item === 'string') return item;
            if (item && typeof item.msg === 'string') {
              const field =
                item.loc && item.loc.length > 0
                  ? `${item.loc[item.loc.length - 1]}: `
                  : '';
              return `${field}${item.msg}`;
            }
            return null;
          })
          .filter((msg): msg is string => Boolean(msg));

        if (messages.length > 0) {
          return messages.join('; ');
        }
      }
    }

    if (typeof record.message === 'string' && record.message) {
      return record.message;
    }

    if (typeof record.error === 'string' && record.error) {
      return record.error;
    }
  }

  return 'An unexpected error occurred.';
}
