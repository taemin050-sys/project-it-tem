import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  return {
    plugins: [react()],
    // 개발 중 /api는 같은 출처로 받아 서버로 넘긴다 (레거시 서버에 CORS 설정이 없음).
    // 대상은 팀이 허가한 서버만. 브라우저 기준 127.0.0.1은 사용자 PC다
    server: { proxy: { '/api': env.VITE_API_PROXY_TARGET || 'http://localhost:8000' } },
  }
})
