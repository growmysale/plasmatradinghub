import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// Detect if running inside Tauri
const isTauri = !!process.env.TAURI_ENV_PLATFORM;

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  // Prevent vite from obscuring Rust errors
  clearScreen: false,

  server: {
    port: isTauri ? 1420 : 3000,
    // Tauri expects a fixed port
    strictPort: true,
    // Only proxy in non-Tauri dev mode (Tauri app talks directly to API)
    ...(!isTauri && {
      proxy: {
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        },
        '/ws': {
          target: 'ws://localhost:8000',
          ws: true,
        },
      },
    }),
  },

  // Environment variables available to the app
  envPrefix: ['VITE_', 'TAURI_ENV_'],

  build: {
    // Tauri uses Chromium on Windows and WebKit on macOS/Linux
    target: isTauri ? 'chrome105' : 'esnext',
    // Produce sourcemaps for debugging
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
    // Output to dist/ for both Vite and Tauri
    outDir: 'dist',
  },
})
