import { defineConfig } from 'vite';
import { nkzModulePreset } from '@nekazari/module-builder';
import path from 'path';

export default defineConfig(
  nkzModulePreset({
    viteConfig: {
      resolve: {
        alias: {
          '@': path.resolve(__dirname, './src'),
        },
      },
      server: {
        port: 5005,
        proxy: {
          '/api': {
            target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
            changeOrigin: true,
            secure: false,
          },
        },
      },
    }
  })
);
