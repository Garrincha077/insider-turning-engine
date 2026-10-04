import { expect, test } from '@playwright/test';
import { fetchSnapshotBytes, readBoundedBody, type SnapshotTransfer } from '../lib/publication-transfer';

test('streamed progress counts received bytes without marking an unverified snapshot as ready', async () => {
  const updates: SnapshotTransfer[] = [];
  const response = new Response(new ReadableStream<Uint8Array>({ start(controller) {
    controller.enqueue(new Uint8Array([1, 2])); controller.enqueue(new Uint8Array([3, 4])); controller.close();
  } }));
  const bytes = await readBoundedBody(response, 4, new AbortController().signal, 'fixture', (update) => updates.push(update));
  expect([...new Uint8Array(bytes)]).toEqual([1, 2, 3, 4]);
  expect(updates[0]).toEqual({ received: 0, total: 4, phase: 'download' });
  expect(updates.at(-1)).toEqual({ received: 4, total: 4, phase: 'verify' });
});

test('declared size overflow is rejected before buffering excess data', async () => {
  await expect(readBoundedBody(new Response(new Uint8Array(5)), 4,
    new AbortController().signal, 'fixture')).rejects.toThrow('integrity mismatch: exceeds declared size');
});

test('invalid declared size cannot become an allocation or false progress denominator', async () => {
  for (const size of [0, -1, NaN, 1.5, 513 * 1024 * 1024])
    await expect(readBoundedBody(new Response('x'), size,
      new AbortController().signal, 'fixture')).rejects.toThrow('invalid declared size');
});

test('download deadline covers a stalled response body, not only headers', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(new ReadableStream<Uint8Array>({ start() {} }));
  try {
    await expect(fetchSnapshotBytes('/fixture', 'fixture', 4, new AbortController().signal,
      undefined, 20)).rejects.toThrow('download timed out');
  } finally { globalThis.fetch = original; }
});

test('parent cancellation stops the body read without being misreported as a timeout', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => new Response(new ReadableStream<Uint8Array>({ start() {} }));
  const parent = new AbortController();
  const pending = fetchSnapshotBytes('/fixture', 'fixture', 4, parent.signal, undefined, 1000);
  setTimeout(() => parent.abort(new Error('user cancellation')), 10);
  try { await expect(pending).rejects.toThrow('user cancellation'); }
  finally { globalThis.fetch = original; }
});

test('file HTTP caching is revalidated and does not replace manifest hash verification', async () => {
  const original = globalThis.fetch;
  let cache: RequestCache | undefined;
  globalThis.fetch = async (_input, init) => { cache = init?.cache; return new Response('okay'); };
  try {
    expect(new TextDecoder().decode(await fetchSnapshotBytes('/fixture', 'fixture', 4,
      new AbortController().signal))).toBe('okay');
    expect(cache).toBe('no-cache');
  } finally { globalThis.fetch = original; }
});
