import { defineConfig } from 'vite'

// GitHub Pages serves the project at /Schofield/; dev stays at /.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/Schofield/' : '/',
  server: { host: true },
  build: { chunkSizeWarningLimit: 1200 },
}))
