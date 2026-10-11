import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
declare const process: { env: Record<string, string | undefined> };
export default defineConfig({ plugins: [react()], server: { hmr: process.env.REFUTELLA_E2E_PORT ? false : undefined, proxy: { '/api': process.env.REFUTELLA_API_TARGET || 'http://127.0.0.1:8000' } } });
