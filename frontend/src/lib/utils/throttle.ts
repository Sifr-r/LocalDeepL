/**
 * Utility functions for throttling event handlers and state updates.
 */

/**
 * Throttles execution of a function using requestAnimationFrame.
 * Guarantees that fn is invoked at most once per animation frame with the latest arguments.
 */
export function rafThrottle<T extends (...args: any[]) => void>(fn: T): T {
  let scheduledFrameId: number | null = null;
  let lastArgs: Parameters<T> | null = null;

  const throttled = (...args: Parameters<T>): void => {
    lastArgs = args;

    if (scheduledFrameId !== null) {
      return;
    }

    if (typeof window === 'undefined' || typeof requestAnimationFrame !== 'function') {
      fn(...args);
      return;
    }

    scheduledFrameId = requestAnimationFrame(() => {
      scheduledFrameId = null;
      if (lastArgs) {
        const currentArgs = lastArgs;
        lastArgs = null;
        fn(...currentArgs);
      }
    });
  };

  return throttled as T;
}
