import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0', // Allow external connections (Docker)
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:28000', // Application backend port: 2xxxx
        changeOrigin: true,
        secure: false,
        // CRITICAL: Preserve cookies for session authentication
        cookieDomainRewrite: '',
        cookiePathRewrite: '/',
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
