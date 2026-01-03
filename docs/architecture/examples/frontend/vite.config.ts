/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Vite Configuration
// vite.config.ts
// Reference: docs/architecture/application-architecture.md § 5 (Vite Frontend Setup)
// CRITICAL NOTES:
// - React plugin MUST be configured (JSX/TSX support)
// - Path alias @/ points to src/ directory (standard Vite pattern)
// - Build target: esnext (modern browsers, no IE11 support)
// - Minification: esbuild (fast, standard Vite default)
// - Sourcemaps disabled in production (security: no source disclosure)
// - Server port MUST be configured via environment variables (no hardcoding port 5173)
// - Development proxy MUST forward to backend API (/api/v1 → http://localhost:8000/api/v1)
// - CORS configuration MUST match backend CORS_ORIGINS environment (security-model.md § 3.2)
// - No API_KEY, secrets, or credentials in vite.config.ts (use .env files only)
// Source: docs/architecture/application-architecture.md § 5, security-model.md § 3.2
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    target: 'esnext',
    minify: 'esbuild',
    sourcemap: process.env.NODE_ENV !== 'production',
  },
  server: {
    port: 20000,
    host: true,
  },
})

