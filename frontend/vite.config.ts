import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    svelte()
  ],
  // Vitest picks this block up automatically because vitest is a
  // dev-dependency. Defaulting the test environment to jsdom keeps the
  // editing-stream sentinel contract test (and any future DOM-touching
  // specs) consistent with the rest of the frontend without per-file
  // `/// @vitest-environment` annotations.
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.ts'],
    // Polyfill modern DOM primitives (DOMMatrix, DOMPoint, …) that
    // ``pdfjs-dist`` touches at module load. Without this, importing
    // the preview store from a unit test throws ReferenceError before
    // any assertion runs.
    setupFiles: ['./src/__tests__/setup.ts']
  },
  base: '/static/',
  resolve: {
    conditions: process.env.VITEST ? ['browser'] : undefined,
    alias: {
      '$lib': path.resolve(__dirname, './src/lib')
    }
  },
  build: {
    // Output directly to omniscribe package static directory
    outDir: path.resolve(__dirname, '../src/omniscribe/static'),
    emptyOutDir: true,
    target: 'esnext',
    // 750 kB catches the actual main-bundle regression (~74 kB) while
    // silencing noise for the intentionally large pdf.worker chunk
    // (~2.2 MB). The previous 3000 kB threshold was effectively a
    // no-op for the real outlier.
    chunkSizeWarningLimit: 750,
    rollupOptions: {
      input: path.resolve(__dirname, 'index.html'),
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('pdfjs-dist')) {
              return 'pdfjs-vendor';
            }
            return 'vendor';
          }
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true
      }
    }
  }
});
