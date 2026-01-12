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
        // In Docker, use service name 'backend' on internal port 8000
        // Vite proxy runs inside Docker container, so it must use Docker network service name
        target: 'http://backend:8000',
        changeOrigin: true,
        secure: false,
        // CRITICAL: Preserve cookies for session authentication
        // These settings ensure cookies are properly forwarded
        cookieDomainRewrite: '',
        cookiePathRewrite: '/',
        // CRITICAL: Configure proxy to preserve all headers including Set-Cookie
        configure: (proxy, _options) => {
          proxy.on('proxyRes', (proxyRes, req, res) => {
            // Log and preserve Set-Cookie headers from backend
            const setCookieHeaders = proxyRes.headers['set-cookie'];
            if (setCookieHeaders && Array.isArray(setCookieHeaders) && setCookieHeaders.length > 0) {
              // Log the actual cookie values for debugging
              console.log('[Vite Proxy] Set-Cookie headers detected:', setCookieHeaders.length, 'cookies');
              setCookieHeaders.forEach((cookie, idx) => {
                console.log(`[Vite Proxy] Cookie ${idx + 1}:`, cookie.substring(0, 50) + '...');
              });
            } else if (setCookieHeaders) {
              console.log('[Vite Proxy] Set-Cookie headers (non-array):', typeof setCookieHeaders, setCookieHeaders);
            }
            // Note: http-proxy-middleware should automatically forward Set-Cookie headers
            // We don't need to manually set them as that could cause conflicts
          });
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
