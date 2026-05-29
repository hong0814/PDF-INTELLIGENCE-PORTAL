import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindCss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindCss()],
  server: {
    proxy: {
      '/api': process.env.VITE_API_BASE_URL ?? 'http://localhost:8111',
    },
  },
})
