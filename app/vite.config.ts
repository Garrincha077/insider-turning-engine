import path from 'node:path';

import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { defineConfig } from 'vite';

const configuredBase = process.env.PAGES_BASE_PATH?.replace(/^\/+|\/+$/g, '') ?? '';

export default defineConfig(({ command }) => {
  const fixtures = process.env.ITE_E2E_FIXTURES === '1';
  if (command === 'build' && fixtures) throw new Error('E2E fixtures cannot enter a production build');
  return {
    publicDir: fixtures ? 'e2e/public' : 'public',
    base: configuredBase ? `/${configuredBase}/` : '/',
    css: { postcss: { plugins: [tailwindcss()] } },
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, '.') } },
    build: { outDir: 'dist', emptyOutDir: true },
  };
});
