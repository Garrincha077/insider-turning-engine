/**
 * Verify the actual published Pages PWA without any production writes.
 * In particular, financial data must not enter the service-worker cache.
 */
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';

assert.ok(process.env.PWA_SITE_URL, 'PWA_SITE_URL is required');
const site = new URL(process.env.PWA_SITE_URL);
assert.equal(site.protocol, 'https:');
assert.ok(site.pathname.endsWith('/'), 'The app URL must include the scoped trailing slash');
const scope = site.pathname;

async function get(path, limit = 50 * 1024 * 1024) {
  const url = new URL(path, site);
  assert.equal(url.origin, site.origin, 'External resource: ' + url);
  assert.ok(url.pathname.startsWith(scope), 'Resource escapes app scope: ' + url);
  const res = await fetch(url, {
    headers: { 'Cache-Control': 'no-cache' },
    signal: AbortSignal.timeout(30_000),
  });
  assert.equal(res.status, 200, 'Unexpected live HTTP ' + res.status + ': ' + url);
  const landed = new URL(res.url);
  assert.equal(landed.origin, site.origin, 'Unexpected origin redirect');
  assert.equal(landed.pathname, url.pathname, 'Unexpected path redirect');
  const bytes = Buffer.from(await res.arrayBuffer());
  assert.ok(bytes.length > 0 && bytes.length <= limit, 'Unexpected resource size: ' + url);
  return { bytes, text: bytes.toString('utf8'), type: res.headers.get('content-type') ?? '' };
}

const page = await get('');
assert.match(page.type, /text\/html/);
assert.ok(page.text.includes('href="' + scope + 'manifest.webmanifest"'), 'Wrong HTML install link');
const assets = [...page.text.matchAll(/(?:src|href)=["']([^"']*\/assets\/[^"']+\.(?:js|css))["']/g)]
  .map((match) => new URL(match[1], site).pathname);
assert.ok(assets.some((x) => x.endsWith('.js')) && assets.some((x) => x.endsWith('.css')),
  'Production JS/CSS assets missing');
assert.ok(assets.every((x) => x.startsWith(scope + 'assets/')), 'Wrong Vite asset base');

const manifest = JSON.parse((await get('manifest.webmanifest')).text);
for (const key of ['id', 'start_url', 'scope']) assert.equal(manifest[key], scope);
assert.equal(manifest.display, 'standalone');
for (const size of [192, 512]) {
  const icon = manifest.icons.find((x) => x.sizes === size + 'x' + size);
  assert.ok(icon && icon.type === 'image/png', 'Invalid icon ' + size);
  const { bytes } = await get(icon.src, 2 * 1024 * 1024);
  assert.equal(bytes.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
  assert.equal(bytes.readUInt32BE(16), size);
  assert.equal(bytes.readUInt32BE(20), size);
}
const worker = (await get('service-worker.js', 1024 * 1024)).text;
assert.ok(worker.includes('const APP_BASE = ' + JSON.stringify(scope) + ';'));
assert.match(worker, /url\.pathname\.startsWith\(DATA_PREFIX\)\) return/);
assert.ok(!worker.includes('cache.put('), 'Unapproved dynamic caching');
const match = worker.match(/^const PRECACHE = (.+);$/m);
assert.ok(match, 'Missing shell precache');
const precache = JSON.parse(match[1]);
assert.ok(precache.includes(scope));
assert.ok(assets.every((x) => precache.includes(x)));
assert.ok(precache.every((x) => x.startsWith(scope) && !x.includes('/data/')),
  'Financial data or outside-scope content in SW cache');
for (const path of new Set(precache)) await get(path, 12 * 1024 * 1024);

// Mandatory files only: large research is verified by the app when requested.
const publication = JSON.parse((await get('data/manifest.json', 4 * 1024 * 1024)).text);
assert.equal(publication.schemaVersion, '1.0.0');
assert.ok(Array.isArray(publication.files));
for (const name of ['dashboard.json', 'settings-status.json']) {
  const entries = publication.files.filter((x) => x.path === name);
  assert.equal(entries.length, 1, 'Missing or duplicated manifest entry: ' + name);
  const pinned = entries[0];
  assert.ok(Number.isSafeInteger(pinned.size) && pinned.size > 0);
  assert.match(pinned.sha256, /^[0-9a-f]{64}$/);
  const file = (await get('data/' + name)).bytes;
  assert.equal(file.length, pinned.size, name + ' size mismatch');
  assert.equal(createHash('sha256').update(file).digest('hex'), pinned.sha256,
    name + ' SHA-256 mismatch');
}
console.log(JSON.stringify({
  result: 'LIVE_PWA_VERIFIED', site: site.toString(),
  shellResources: new Set(precache).size,
  financialDataCached: false, verifiedFiles: ['dashboard.json', 'settings-status.json'],
}));
