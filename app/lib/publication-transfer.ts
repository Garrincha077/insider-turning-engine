export type SnapshotTransfer = { received: number; total: number; phase: 'download' | 'verify' };
const MAX_BYTES = 512 * 1024 * 1024;

export async function withDownloadDeadline<T>(parent: AbortSignal, name: string,
  work: (signal: AbortSignal) => Promise<T>, timeoutMs = 180_000): Promise<T> {
  parent.throwIfAborted();
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort(parent.reason);
  parent.addEventListener('abort', cancel, { once: true });
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try { return await work(controller.signal); }
  catch (error) {
    if (timedOut && !parent.aborted) throw new Error(`${name} download timed out. Retry snapshot when the connection is available; no sample data is substituted.`);
    throw error;
  } finally { clearTimeout(timer); parent.removeEventListener('abort', cancel); }
}

export async function readBoundedBody(response: Response, size: number, signal: AbortSignal,
  name: string, onProgress?: (progress: SnapshotTransfer) => void): Promise<ArrayBuffer> {
  if (!Number.isSafeInteger(size) || size <= 0 || size > MAX_BYTES) throw new Error(`${name} invalid declared size`);
  signal.throwIfAborted();
  const reader = response.body?.getReader();
  if (!reader) throw new Error(`${name} response body unavailable`);
  const chunks: Uint8Array[] = [];
  let received = 0, reported = 0, lastUpdate = performance.now();
  const cancel = () => { void reader.cancel(signal.reason).catch(() => {}); };
  signal.addEventListener('abort', cancel, { once: true });
  onProgress?.({ received: 0, total: size, phase: 'download' });
  try {
    while (true) {
      const { done, value } = await reader.read();
      signal.throwIfAborted();
      if (done) break;
      received += value.byteLength;
      if (received > size) {
        await reader.cancel();
        throw new Error(`${name} integrity mismatch: exceeds declared size`);
      }
      chunks.push(value);
      if (received - reported >= 1_000_000 || performance.now() - lastUpdate >= 300) {
        onProgress?.({ received, total: size, phase: 'download' });
        reported = received; lastUpdate = performance.now();
      }
    }
  } finally { signal.removeEventListener('abort', cancel); reader.releaseLock(); }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  onProgress?.({ received, total: size, phase: 'verify' });
  return bytes.buffer;
}

export async function fetchSnapshotBytes(url: string, name: string, size: number,
  signal: AbortSignal, onProgress?: (progress: SnapshotTransfer) => void, timeoutMs = 180_000) {
  return withDownloadDeadline(signal, name, async (requestSignal) => {
    onProgress?.({ received: 0, total: size, phase: 'download' });
    // Revalidate HTTP cache entries, then always verify their bytes against the
    // current manifest. This is not a stale-data or sample fallback.
    const response = await fetch(url, { cache: 'no-cache', signal: requestSignal });
    if (!response.ok) throw new Error(`${name} unavailable`);
    return readBoundedBody(response, size, requestSignal, name, onProgress);
  }, timeoutMs);
}
