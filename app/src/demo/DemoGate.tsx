import { useEffect, useState } from 'react'
import App from '../App'
import { useProjectStore } from '../store/projectStore'
import DemoEvaluation from './DemoEvaluation'
import DemoLiveConsole from './DemoLiveConsole'
import { Link, useLocation } from 'react-router-dom'

type Identity = { authenticated: true; evaluator_id: string; role: 'evaluator' | 'admin'; mode: 'MOCK' }

export default function DemoGate() {
  const { pathname } = useLocation()
  const livePage = pathname === '/demo/live'
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [checking, setChecking] = useState(true)
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const setJobId = useProjectStore((s) => s.setJobId)
  useEffect(() => {
    let active = true
    fetch('/demo/api/session', { credentials: 'same-origin', cache: 'no-store' })
      .then(async r => r.ok ? (await r.json() as Identity) : null)
      .then(v => { if (active) setIdentity(v) })
      .catch(() => { if (active) setError('서버에 연결할 수 없습니다. Mock 데이터로 전환하지 않습니다.') })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [])
  async function login() {
    setBusy(true); setError('')
    try {
      const r = await fetch('/demo/api/session', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: invite }),
      })
      if (!r.ok) throw Error('초대코드가 유효하지 않거나 로그인 횟수 제한에 도달했습니다.')
      const who = await r.json() as Identity
      setJobId(null)
      setIdentity(who); setInvite('')
    } catch (e) { setError(e instanceof Error ? e.message : '로그인 실패') }
    finally { setBusy(false) }
  }
  async function logout() {
    try { await fetch('/demo/api/session', {method: 'DELETE', credentials: 'same-origin'}) }
    finally { setJobId(null); setIdentity(null) }
  }
  if (checking) return <div role="status" style={{padding: 32}}>개인별 시연 권한을 확인하고 있습니다…</div>
  if (!identity) return <main style={{maxWidth: 560, margin: '8vh auto', padding: 30}}>
    <h1>IT-TEM 원격 시연</h1>
    <p><strong>DEMO · MOCK ONLY</strong> — 실제 생성 AI 또는 규제 검수가 아닙니다.</p>
    <p>Cloudflare 이메일 PIN 인증을 마친 뒤, 개인별 초대코드를 입력해 주세요.</p>
    <form onSubmit={e => {e.preventDefault();void login()}}>
      <label htmlFor="demo-invite">개인별 초대코드</label>
      <input id="demo-invite" type="password" autoComplete="off" required minLength={20}
        value={invite} onChange={e => setInvite(e.target.value)} style={{width:'100%', margin:'10px 0'}} />
      <button type="submit" disabled={busy}>{busy ? '검증 중…' : '시연 시작'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
  </main>
  return <>
    <aside style={{padding:'9px 14px',background:'#202b3b',color:'white',display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:10}}>
      <span><strong>IT-TEM DEMO — MOCK</strong> · AI 미호출 · 법률 검수 미수행 · 결과는 평가용</span>
      <span>{identity.evaluator_id} · <button type="button" onClick={() => void logout()}>로그아웃</button></span>
    </aside>
    <nav style={{padding:'10px 18px',display:'flex',gap:18}}>
      <Link to="/">검증된 B0 Mock</Link>
      <Link to="/demo/live">실제 AI Live (비용 승인 필요)</Link>
    </nav>
    {livePage ? <DemoLiveConsole /> : <>
      <App />
      <DemoEvaluation identity={identity} />
    </>}
  </>
}
