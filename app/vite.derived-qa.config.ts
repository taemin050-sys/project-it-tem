// Separate loopback-only fixture entry. The normal production input is unchanged.
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {host: '127.0.0.1', port: 18425, strictPort: true,
    proxy: {'/demo/api': 'http://127.0.0.1:18325', '/__derived_qa__': 'http://127.0.0.1:18325'}},
  build: {outDir: '/private/tmp/ittem-h6-derived-qa-dist', emptyOutDir: false,
    rollupOptions: {input: 'derived-qa.html'}},
})
