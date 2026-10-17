import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // The optional PDF renderer is lazy-loaded and intentionally isolated from the app shell.
  build: { chunkSizeWarningLimit: 1300 },
})
