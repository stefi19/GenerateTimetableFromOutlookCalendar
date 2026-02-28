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
    // target a reasonably modern ES version for broad compatibility
    target: 'es2019',
    // ── Production optimizations ──
    // Enable source maps for debugging (disable in ultra-lean builds)
    sourcemap: false,
    // Increase chunk size warning limit (we optimize via splitting)
    chunkSizeWarningLimit: 600,
    // Minification with esbuild (fastest) — terser is slower but smaller
    minify: 'esbuild',
    // CSS code splitting for better caching
    cssCodeSplit: true,
    // Rollup options for optimal chunk splitting
    rollupOptions: {
      output: {
        // Split vendor chunks for better caching
        manualChunks: {
          'react-vendor': ['react', 'react-dom'],
        },
        // Use content hashes for cache busting
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
  },
  // Dependency pre-bundling optimization
  optimizeDeps: {
    include: ['react', 'react-dom'],
  },
})
