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
    emptyDirBeforeWrite: true
  }
})
