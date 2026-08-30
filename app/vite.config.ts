import path from 'node:path';

import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { defineConfig } from 'vite';

const configuredBase = process.env.PAGES_BASE_PATH?.replace(/^\/+|\/+$/g, '') ?? '';

export default defineConfig({
  base: configuredBase ? `/${configuredBase}/` : '/',
  css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, '.') } },
  build: { outDir: 'dist', emptyOutDir: true },
});
