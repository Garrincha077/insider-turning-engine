/** Validate PWA build output without a network or a browser. */
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const segment = (process.env.PAGES_BASE_PATH ?? '').replace(/^\/+|\/+$/g, '');
const base = segment ? '/' + segment + '/' : '/';
const manifest = JSON.parse(readFileSync(join(root, 'manifest.webmanifest'), 'utf8'));
assert.equal(manifest.start_url, base);
assert.equal(manifest.id, base);
assert.equal(manifest.scope, base);
assert.equal(manifest.display, 'standalone');
assert.match(manifest.name, /Insider Turning Engine/);
for (const size of [192, 512]) {
  const icon = manifest.icons.find((item) => item.sizes === size + 'x' + size);
  assert.ok(icon);
  assert.equal(icon.type, 'image/png');
  assert.ok(icon.src.startsWith(base));
  const bytes = readFileSync(join(root, icon.src.slice(base.length)));
  assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(bytes.readUInt32BE(16), size);
  assert.equal(bytes.readUInt32BE(20), size);
  assert.equal(bytes[25], 6); // opaque RGBA content is generated for Android
}
const html = readFileSync(join(root, 'index.html'), 'utf8');
assert.match(html, /rel="manifest"/);
assert.match(html, /name="theme-color"/);
const worker = readFileSync(join(root, 'service-worker.js'), 'utf8');
const match = worker.match(/^const PRECACHE = (.+);$/m);
assert.ok(match, 'missing static shell precache');
const paths = JSON.parse(match[1]);
assert.ok(paths.includes(base));
assert.ok(paths.some((p) => p.includes('/assets/') && p.endsWith('.js')));
assert.ok(paths.some((p) => p.includes('/assets/') && p.endsWith('.css')));
for (const url of paths) {
  assert.ok(url.startsWith(base), url);
  assert.ok(!url.includes('/data/'), 'Financial data must never be precached');
  const name = url === base ? 'index.html' : url.slice(base.length);
  assert.ok(existsSync(join(root, name)), name + ' does not exist in dist');
}
assert.match(worker, /url\.pathname\.startsWith\(DATA_PREFIX\)\) return/);
assert.ok(!worker.includes('cache.put('));
assert.ok(!worker.includes('caches.open(DATA_PREFIX'));
console.log(JSON.stringify({
  status: 'PWA_BUILD_VERIFIED', scope: base, icons: [192, 512],
  shellResources: paths.length, cachedData: false,
}));
