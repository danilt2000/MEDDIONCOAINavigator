import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const apiTarget = process.env.API_TARGET ?? 'http://localhost:8100';

export default defineConfig({
  plugins: [react()],
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { port: 5174, proxy: { '/api': apiTarget, '/mock': apiTarget } },
});
