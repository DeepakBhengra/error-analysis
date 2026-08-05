import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { startApiPlugin } from './startApiPlugin'

export default defineConfig({
  plugins: [react(), startApiPlugin()],
  server: {
    // Prefer 5173; Vite will try the next free port (e.g. 5174) if busy.
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
