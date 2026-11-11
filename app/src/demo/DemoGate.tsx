import { useEffect, useState } from 'react'
import App from '../App'
import { useProjectStore } from '../store/projectStore'
import DemoEvaluation from './DemoEvaluation'
import DemoLiveConsole from './DemoLiveConsole'
import { Link, useLocation } from 'react-router-dom'
import {QA_OFFLINE_FIXTURE} from '../config'
import { continueOrStartNew } from '../api/useJob'
const SSO_ONLY = import.meta.env.VITE_IT_TEM_SSO_ONLY === 'YES'
const SIGNED_NONBILLABLE_CANDIDATE = import.meta.env.VITE_A51E_SIGNED_BETA_CANDIDATE === 'YES'
const TRACK_LABEL = import.meta.env.VITE_IT_TEM_TRACK_ID === 'ENHANCED' ? 'BP18 ENHANCED / PROVISIONAL' : import.meta.env.VITE_IT_TEM_TRACK_ID === 'BASELINE' ? 'BP18 BASELINE' : 'IT-TEM'

type Identity = { authenticated: true; evaluator_id: string; role: 'evaluator' | 'admin';
  auth_provider?: 'TAILSCALE_SERVE'|'INVITE_COOKIE'; mode: string }

export default function DemoGate() {
  const { pathname } = useLocation()
  const diagnosticPage = pathname === '/internal/live-diagnostics'
  const [identity, setIdentity] = useState<Identity | null>(null)
  const [checking, setChecking] = useState(true)
  const [invite, setInvite] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const setJobId = useProjectStore((s) => s.setJobId)
  const setIdentityScope=useProjectStore((s)=>s.setIdentityScope)
  useEffect(() => {
    let active = true
    fetch('/demo/api/session', { credentials: 'same-origin', cache: 'no-store' })
      .then(async r => r.ok ? (await r.json() as Identity) : null)
      .then(v => { if (active) {setIdentityScope(v?.evaluator_id??null);setIdentity(v)} })
      .catch(() => { if (active) setError('서버에 연결할 수 없습니다. Mock 데이터로 전환하지 않습니다.') })
      .finally(() => { if (active) setChecking(false) })
    return () => { active = false }
  }, [setIdentityScope])
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
      setIdentityScope(who.evaluator_id)
      setJobId(null)
      setIdentity(who); setInvite('')
    } catch (e) { setError(e instanceof Error ? e.message : '로그인 실패') }
    finally { setBusy(false) }
  }
  async function logout() {
    try { await fetch('/demo/api/session', {method: 'DELETE', credentials: 'same-origin'}) }
    finally { setIdentityScope(null);setJobId(null); setIdentity(null) }
  }
  if (checking) return <div role="status" style={{padding: 32}}>Tailscale 팀원 인증을 확인하고 있습니다…</div>
  if (!identity && SSO_ONLY) return <main style={{maxWidth: 560, margin: '8vh auto', padding: 30}}>
    <h1>IT-TEM 접근 권한 확인 필요</h1>
    <p>등록된 팀원만 Tailscale SSO를 통해 자동 로그인할 수 있습니다.</p>
    <p>Tailscale 연결 상태와 팀원 등록 여부를 관리자에게 확인해 주세요.</p>
    {error && <p role="alert">{error}</p>}
  </main>
  if (!identity) return <main style={{maxWidth: 560, margin: '8vh auto', padding: 30}}>
    <h1>{TRACK_LABEL} 원격 시연</h1>
    <p><strong>{QA_OFFLINE_FIXTURE || SIGNED_NONBILLABLE_CANDIDATE
      ? 'IT-TEM Signed SSO 비과금 통합 검증 · 실제 AI 호출 없음'
      : 'IT-TEM 실제 AI Live 평가'}</strong> — 승인된 구성원에게만 제공됩니다.</p>
    <p>승인된 Tailscale 네트워크에서 접속해 주세요. 자동 로그인되지 않으면 관리자에게 문의하세요.</p>
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
      <span><strong>{TRACK_LABEL} · {SIGNED_NONBILLABLE_CANDIDATE
        ? 'Signed SSO 비과금 후보 · 실모델 기술 게이트 미충족'
        : QA_OFFLINE_FIXTURE ? 'IT-TEM QA OFFLINE_FIXTURE · 실제 AI 아님'
        : 'IT-TEM 제품 검증 · 실모델 Worker 비활성'}</strong>
        {' · '}{SIGNED_NONBILLABLE_CANDIDATE
          ? 'MPO 업로드 거절 정책 적용 · Worker 비활성 · 합성 시험 데이터 전용'
          : QA_OFFLINE_FIXTURE
            ? '시험 데이터 / 유료 호출 없음'
            : '승인된 팀원용 입력 검증 · 실제 AI 호출 비활성 · MONITOR_ONLY'}{' · '}
        <small>Build {import.meta.env.VITE_IT_TEM_CODE_SHA?.slice(0,8) || 'UNPINNED'}</small></span>
      <span>{identity.evaluator_id} · {identity.auth_provider==='TAILSCALE_SERVE'
        ? <span aria-label="Tailscale 신원 확인 완료">Tailscale 인증됨</span>
        : <button type="button" onClick={() => void logout()}>로그아웃</button>}</span>
    </aside>
    <nav style={{padding:'10px 18px',display:'flex',gap:18}}>
      <Link to="/">정식 IT-TEM 시작</Link>
      <Link to="/create" onClick={continueOrStartNew}>{QA_OFFLINE_FIXTURE ? 'QA 시험 광고 생성' : SIGNED_NONBILLABLE_CANDIDATE ? '비과금 광고 입력 검증' : '실제 AI 광고 생성'}</Link>
      {!QA_OFFLINE_FIXTURE && <Link to="/team/evaluations">팀 공동 품질 평가</Link>}
      {identity.role==='admin' && <Link to="/internal/live-diagnostics">내부 진단</Link>}
    </nav>
    {diagnosticPage && identity.role==='admin'
      ? <DemoLiveConsole evaluatorId={identity.evaluator_id}/>
      : <><App />{import.meta.env.DEV && useProjectStore.getState().mock &&
        <DemoEvaluation identity={identity as Parameters<typeof DemoEvaluation>[0]['identity']} />}</>}
  </>
}
