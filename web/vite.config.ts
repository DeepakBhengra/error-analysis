import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { startApiPlugin } from './startApiPlugin'

function parsePort(value: string | undefined, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devHost = env.VITE_DEV_HOST || '127.0.0.1'
  const devPort = parsePort(env.VITE_DEV_PORT || env.PORT, 5173)
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8010'
  const strictPort = env.VITE_DEV_STRICT_PORT === '1' || env.VITE_DEV_STRICT_PORT === 'true'

  return {
    plugins: [react(), startApiPlugin()],
    server: {
      host: devHost,
      port: devPort,
      strictPort,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
