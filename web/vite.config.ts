import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'path';

const proxyTarget =
  process.env.VITE_API_PROXY_URL ||
  process.env.VITE_API_URL ||
  'http://localhost:8000';

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    // HMR configuration for Docker
    hmr: {
      host: 'localhost',
      port: 5173,
    },
    watch: {
      usePolling: true, // Required for Docker volume mounts
    },
    proxy: {
      '^/voice$': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});
