/**
 * Generate installable Android assets with no third-party runtime dependencies.
 * Only the small application shell is cached. Published financial data is never cached.
 */
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';

const dist = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');
const segment = (process.env.PAGES_BASE_PATH ?? '').replace(/^\/+|\/+$/g, '');
if (segment && !/^[a-zA-Z0-9_.-]+$/.test(segment)) {
  throw new Error('Invalid PAGES_BASE_PATH');
}
const base = segment ? '/' + segment + '/' : '/';

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let i = 0; i < 8; i++) {
      crc = (crc & 1) ? (crc >>> 1) ^ 0xedb88320 : (crc >>> 1);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, bytes) {
  const tag = Buffer.from(type);
  const len = Buffer.alloc(4);
  len.writeUInt32BE(bytes.length);
  const checksum = Buffer.alloc(4);
  checksum.writeUInt32BE(crc32(Buffer.concat([tag, bytes])));
  return Buffer.concat([len, tag, bytes, checksum]);
}

function mix(baseColor, accent, strength) {
  return Math.round(baseColor * (1 - strength) + accent * strength);
}

/** Opaque and centered radar mark stays inside Android maskable icon safe area. */
function icon(size) {
  const stride = size * 4 + 1;
  const pixels = Buffer.alloc(stride * size);
  for (let y = 0; y < size; y++) {
    const row = y * stride;
    pixels[row] = 0;
    for (let x = 0; x < size; x++) {
      const nx = (x + 0.5 - size / 2) / size;
      const ny = (y + 0.5 - size / 2) / size;
      const radius = Math.hypot(nx, ny);
      const haze = Math.max(0, 1 - radius / 0.8) * 0.24;
      let red = mix(9, 13, haze);
      let green = mix(18, 43, haze);
      let blue = mix(33, 57, haze);
      let rings = 0;
      for (const target of [0.114, 0.224, 0.324]) {
        rings = Math.max(rings, Math.max(0, 1 -
          Math.abs(radius - target) / (size <= 192 ? 0.010 : 0.006)));
      }
      const rx = nx * 0.58 + ny * 0.82;
      const ry = -nx * 0.82 + ny * 0.58;
      const sweep = rx > 0 && rx < 0.31 ?
        Math.max(0, 1 - Math.abs(ry) / 0.008) : 0;
      let points = 0;
      for (const [px, py, rad] of [
        [0.184, -0.158, 0.020], [-0.158, -0.093, 0.014],
      ]) {
        const distance = Math.hypot(nx - px, ny - py);
        points = Math.max(points, Math.max(0,
          Math.min(1, (rad + 0.006 - distance) / 0.006)));
      }
      const light = Math.min(1, rings * 0.48 + sweep * 0.86 + points);
      red = mix(red, 73, light);
      green = mix(green, 229, light);
      blue = mix(blue, 177, light);
      const i = row + 1 + x * 4;
      pixels[i] = red;
      pixels[i + 1] = green;
      pixels[i + 2] = blue;
      pixels[i + 3] = 255;
    }
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 6;
  return Buffer.concat([
    Buffer.from('89504e470d0a1a0a', 'hex'),
    chunk('IHDR', header),
    chunk('IDAT', deflateSync(pixels, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

const html = readFileSync(join(dist, 'index.html'), 'utf8');
const assets = [...html.matchAll(/(?:src|href)=["']([^"']+\/assets\/[^"']+\.(?:js|css))["']/g)]
  .map((match) => new URL(match[1], 'https://pwa.invalid' + base).pathname);
if (!assets.some((p) => p.endsWith('.js')) ||
    !assets.some((p) => p.endsWith('.css')) ||
    assets.some((p) => !p.startsWith(base + 'assets/'))) {
  throw new Error('Unable to prove the Vite production asset paths');
}

const png192 = icon(192);
const png512 = icon(512);
writeFileSync(join(dist, 'icon-192.png'), png192);
writeFileSync(join(dist, 'icon-512.png'), png512);

const manifest = {
  id: base,
  name: 'Insider Turning Engine',
  short_name: 'Insider',
  description: 'Source-linked SEC insider research and market context',
  start_url: base,
  scope: base,
  display: 'standalone',
  background_color: '#091221',
  theme_color: '#091221',
  icons: [
    { src: base + 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
    { src: base + 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
  ],
};
writeFileSync(join(dist, 'manifest.webmanifest'), JSON.stringify(manifest, null, 2) + '\n');

const precache = [...new Set([
  base,
  ...assets,
  base + 'favicon.svg',
  base + 'manifest.webmanifest',
  base + 'icon-192.png',
  base + 'icon-512.png',
])];
if (precache.some((p) => p.includes('/data/') || !p.startsWith(base))) {
  throw new Error('Refusing to precache financial data or URLs outside application scope');
}
const buildId = createHash('sha256').update(html).update(png512).digest('hex').slice(0, 16);
const cachePrefix = 'ite-pwa-shell-' + (segment || 'root') + '-';

// The navigation fallback serves only JavaScript/CSS HTML shell. App fetches
// a fresh no-store manifest and validates data SHA-256 before rendering facts.
const worker = [
  '/* Generated PWA worker. Shell-only cache. Financial publication is network-only. */',
  'const APP_BASE = ' + JSON.stringify(base) + ';',
  'const CACHE_PREFIX = ' + JSON.stringify(cachePrefix) + ';',
  'const CACHE_NAME = CACHE_PREFIX + ' + JSON.stringify(buildId) + ';',
  'const PRECACHE = ' + JSON.stringify(precache) + ';',
  "const DATA_PREFIX = APP_BASE + 'data/';",
  "self.addEventListener('install', (event) => {",
  '  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)));',
  '});',
  "self.addEventListener('activate', (event) => {",
  '  event.waitUntil((async () => {',
  '    const keys = await caches.keys();',
  '    await Promise.all(keys.filter((key) =>',
  '      key.startsWith(CACHE_PREFIX) && key !== CACHE_NAME).map((key) =>',
  '      caches.delete(key)));',
  '    await self.clients.claim();',
  '  })());',
  '});',
  "self.addEventListener('message', (event) => {",
  "  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();",
  '});',
  "self.addEventListener('fetch', (event) => {",
  '  const request = event.request;',
  "  if (request.method !== 'GET') return;",
  '  const url = new URL(request.url);',
  '  if (url.origin !== self.location.origin || !url.pathname.startsWith(APP_BASE)) return;',
  "  if (url.pathname.startsWith(DATA_PREFIX)) return; // NEVER cache financial data.",
  "  if (request.mode === 'navigate') {",
  '    event.respondWith((async () => {',
  "      try { return await fetch(request, { cache: 'no-store' }); }",
  '      catch {',
  '        const cache = await caches.open(CACHE_NAME);',
  '        return (await cache.match(APP_BASE)) || Response.error();',
  '      }',
  '    })());',
  '    return;',
  '  }',
  '  if (PRECACHE.includes(url.pathname)) {',
  '    event.respondWith((async () => {',
  '      const cache = await caches.open(CACHE_NAME);',
  '      return (await cache.match(request)) || fetch(request);',
  '    })());',
  '  }',
  '});',
].join('\n') + '\n';
writeFileSync(join(dist, 'service-worker.js'), worker);
console.log(JSON.stringify({
  status: 'PWA_SHELL_ONLY',
  scope: base,
  iconSizes: [192, 512],
  staticResources: precache.length,
  dataCached: false,
  buildId,
}));
