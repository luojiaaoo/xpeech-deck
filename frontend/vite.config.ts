import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// 生产构建产物直接输出到后端的 static 目录，由 FastAPI 统一托管
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  const backendUrl = env.VITE_BACKEND_URL || 'http://localhost:7801'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': backendUrl,
        '/health': backendUrl,
      },
    },
    build: {
      outDir: '../xpeech_deck/static',
      emptyOutDir: true,
    },
  }
})
