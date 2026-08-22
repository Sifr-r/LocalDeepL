/**
 * Parse the /health response body into a status string.
 * Returns null when the body is empty or unparseable - we treat that
 * as "not online" rather than throwing, because the badge should
 * only flip to "online" on an explicit ok signal from the server.
 */
export function parseHealthBody(res: { status: string } | null): 'ok' | 'not-ok' | null {
  return res === null ? null : res.status === 'ok' ? 'ok' : 'not-ok';
}

/**
 * Classify a ping error. AbortError means the component unmounted
 * or a newer ping superseded this one; in both cases the badge
 * should NOT flip - a superseded ping is not a "backend down"
 * signal, and an unmount mid-ping shouldn't toggle the indicator
 * right as the component tears down.
 */
export function classifyPingError(err: unknown): 'aborted' | 'down' {
  return err instanceof DOMException && err.name === 'AbortError' ? 'aborted' : 'down';
}
