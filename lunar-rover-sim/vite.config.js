import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  base: './',
  resolve: {
    alias: {
      postprocessing: fileURLToPath(new URL('./src/stubs/postprocessing.js', import.meta.url)),
    },
  },
  server: { host: true, port: 5173 },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 2000,
  },
});
