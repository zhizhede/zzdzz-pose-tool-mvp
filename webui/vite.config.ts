import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// base './' 使 dist 可被 FastAPI 在任意路径托管
export default defineConfig({
  plugins: [vue()],
  base: './',
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:7860' },
  },
})
