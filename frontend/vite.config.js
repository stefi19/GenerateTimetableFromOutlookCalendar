import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/frontend/',
  server: {
    proxy: {
      '/events.json': 'http://127.0.0.1:5000',
      '/departures.json': 'http://127.0.0.1:5000',
      '/generate_events': 'http://127.0.0.1:5000',
      '/generate_status': 'http://127.0.0.1:5000',
    }
  },
  build: {
    outDir: 'dist',
    emptyDirBeforeWrite: true,
    // target a reasonably modern ES version to improve compatibility with
    // older Safari versions that may throw "Cannot access uninitialized variable".
    // If further compatibility is required consider adding @vitejs/plugin-legacy.
    target: 'es2019'
  }
})
