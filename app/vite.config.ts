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
    // Offline local dev ONLY. Neither production builds nor the pinned
    // GCP OFFLINE_FIXTURE QA may synthesize an authenticated user session.
    plugins: mode === 'development' && env.VITE_USE_MOCK === 'true' &&
      env.VITE_QA_OFFLINE_FIXTURE !== 'YES' ? [react(), mockSession] : [react()],
    // Even when mock login is explicitly enabled the dev server only binds
    // loopback. Never expose the mock-session middleware to teammates.
    server: { host: env.VITE_USE_MOCK === 'true' ? '127.0.0.1' : undefined,
      proxy: { '/api': env.VITE_API_PROXY_TARGET || 'http://localhost:8000' } },
  }
})
