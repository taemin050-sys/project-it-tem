import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv, type Plugin } from 'vite'

// 로그인 게이트(DemoGate)는 배포 서버에 세션을 묻는다. mock 개발 서버에는 그 서버가 없어 세션 응답만 대신한다
const mockSession: Plugin = {
  name: 'mock-session',
  apply: 'serve',
  configureServer(server) {
    server.middlewares.use('/demo/api/session', (_req, res) => {
      res.setHeader('Content-Type', 'application/json')
      res.end(JSON.stringify({ authenticated: true, evaluator_id: 'local-mock', role: 'evaluator', mode: 'MOCK' }))
    })
  },
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  return {
    plugins: env.VITE_USE_MOCK === 'true' ? [react(), mockSession] : [react()],
    // 개발 중 /api는 같은 출처로 받아 서버로 넘긴다 (레거시 서버에 CORS 설정이 없음).
    // 대상은 팀이 허가한 서버만. 브라우저 기준 127.0.0.1은 사용자 PC다
    server: { proxy: { '/api': env.VITE_API_PROXY_TARGET || 'http://localhost:8000' } },
  }
})
