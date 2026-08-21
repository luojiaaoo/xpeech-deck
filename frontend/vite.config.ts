import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 生产构建产物直接输出到后端的 static 目录，由 FastAPI 统一托管
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:7800',
      '/health': 'http://localhost:7800',
    },
  },
  build: {
    outDir: '../xpeech_deck/static',
    emptyOutDir: true,
  },
})
