import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ publicDir: 'public/static', plugins: [react()], server: { proxy: { '/api': 'http://127.0.0.1:8000' } }, preview: { proxy: { '/api': 'http://127.0.0.1:8000' } } });
