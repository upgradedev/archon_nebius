import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    // Vitest owns the unit/component tests under src/ ONLY. The Playwright
    // browser E2E lives in e2e/*.spec.ts and is run by `test:e2e`, not vitest —
    // scope the glob so vitest never tries to import a Playwright spec (which
    // calls test() outside the Playwright runner and throws).
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
