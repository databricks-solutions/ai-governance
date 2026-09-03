import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Frontend builds to ./dist, which FastAPI serves as static files in production.
// In dev, /api is proxied to the FastAPI process on :8000.
export default defineConfig({
  plugins: [react()],
  build: { outDir: 'dist', sourcemap: true },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});
