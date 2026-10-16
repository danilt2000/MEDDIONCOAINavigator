import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      pwaAssets: {},
      workbox: { globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'] },
      manifest: {
        name: 'Onco Navigator',
        short_name: 'Navigator',
        description: 'Your oncology care companion',
        theme_color: '#236488',
        background_color: '#f6fafe',
        display: 'standalone',
      },
    }),
  ],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { port: 5173 },
});
