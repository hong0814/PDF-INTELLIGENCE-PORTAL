import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindCss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindCss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
