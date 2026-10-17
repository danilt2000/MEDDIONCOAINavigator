import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

const apiTarget = process.env.API_TARGET ?? 'http://localhost:8100';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      pwaAssets: {},
      workbox: { globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'], importScripts: ['push-sw.js'] },
      manifest: {
        name: 'MEDDI navigátor',
        short_name: 'MEDDI',
        description: 'Navigátor pro pacienty MOÚ mezi kontrolami',
        lang: 'cs',
        theme_color: '#056b5b',
        background_color: '#f5fbf7',
        display: 'standalone',
      },
    }),
  ],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { port: 5173, proxy: { '/api': apiTarget, '/mock': apiTarget } },
});
