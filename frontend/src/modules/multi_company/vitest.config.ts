import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  cacheDir: fileURLToPath(new URL('../../../.vite-cache/multi-company', import.meta.url)),
  resolve: { alias: { '@': fileURLToPath(new URL('../..', import.meta.url)) } },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/modules/multi_company/**/*.test.{ts,tsx}'],
  },
});
