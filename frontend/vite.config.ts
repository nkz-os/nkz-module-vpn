import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// IIFE bundle config for NKZ module system.
// Module Federation was attempted and abandoned (2026-02-16).
// All modules compile to a single nekazari-module.js that self-registers
// via window.__NKZ__.register() at runtime.
export default defineConfig({
  plugins: [
    react({ jsxRuntime: 'classic' }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5005,
    cors: true,
    proxy: {
      '/api': {
        target: process.env.VITE_DEV_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    lib: {
      entry: path.resolve(__dirname, 'src/moduleEntry.ts'),
      name: 'NekazariModuleVpn',
      formats: ['iife'],
      fileName: () => 'nekazari-module.js',
    },
    rollupOptions: {
      external: [
        'react',
        'react-dom',
        'react-dom/client',
        'react-router-dom',
        '@nekazari/sdk',
        '@nekazari/ui-kit',
      ],
      output: {
        globals: {
          'react': 'React',
          'react-dom': 'ReactDOM',
          'react-dom/client': 'ReactDOM',
          'react-router-dom': 'ReactRouterDOM',
          '@nekazari/sdk': '__NKZ_SDK__',
          '@nekazari/ui-kit': '__NKZ_UI__',
        },
        inlineDynamicImports: true,
      },
    },
    target: 'esnext',
    minify: true,
    cssCodeSplit: false,
  },
});
