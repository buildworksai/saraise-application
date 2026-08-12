import { configDefaults, defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    exclude: [...configDefaults.exclude, '.stryker-tmp/**', '.stryker-tmp*/**'],
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    testTimeout: 15000,
    hookTimeout: 15000,
    maxWorkers: 2,
    minWorkers: 1,
    coverage: {
      enabled: true,
      provider: 'v8',
      reporter: ['text', 'json-summary', 'lcov'],
      reportsDirectory: './coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['**/*.d.ts', 'src/setupTests.ts', '.stryker-tmp/**', '.stryker-tmp*/**'],
    },
  },
});
