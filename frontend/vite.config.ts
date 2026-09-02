import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { quasar, transformAssetUrls } from '@quasar/vite-plugin';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [
    vue({ template: { transformAssetUrls } }),
    quasar({ sassVariables: false }),
  ],
  resolve: {
    alias: {
      src: fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 9000,
    proxy: {
      '/api': {
        // 127.0.0.1, not 'localhost' — on Windows, resolving 'localhost' can add a ~2s
        // IPv6-then-IPv4 fallback delay per request (measured directly, unrelated to the
        // app itself). The explicit loopback address skips DNS resolution entirely.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
    setupFiles: ['tests/setup.ts'],
  },
});
