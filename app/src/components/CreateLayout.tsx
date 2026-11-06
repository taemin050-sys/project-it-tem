import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { startNewAd } from '../api/useJob'
import { SERVICE_NAME } from '../config'
import { STEPS, stepIndex } from '../steps'
import { useProjectStore } from '../store/projectStore'

const STATE_TEXT = { done: '완료', current: '현재 단계', todo: '진행 전' } as const

// 지나온 단계만 되돌아갈 수 있고, 다음 단계는 각 화면의 버튼으로만 넘어간다
export default function CreateLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const busy = useProjectStore((s) => s.run.busy)
  const mock = useProjectStore((s) => s.mock)
  const setMock = useProjectStore((s) => s.setMock)
  const current = stepIndex(pathname)

  return (
    <div className="create">
      <a className="skip-link" href="#create-main">본문 바로가기</a>
      <header className="site-header create-header">
        <div className="container create-header-inner">
          <Link to="/" className="logo" aria-label={`${SERVICE_NAME} 홈`}>{SERVICE_NAME}</Link>
          <nav className="stepper" aria-label="광고 만들기 진행 단계">
            <ol>
              {STEPS.map((s, i) => {
                const state = i < current ? 'done' : i === current ? 'current' : 'todo'
                const content = (
                  <>
                    <span className="stepper-dot" aria-hidden="true">{state === 'done' ? '✓' : i + 1}</span>
                    <span className="stepper-label">{s.label}</span>
                    <span className="visually-hidden"> ({STATE_TEXT[state]})</span>
                  </>
                )
                return (
                  <li key={s.path} className={`stepper-item ${state}`}>
                    {state === 'done'
                      ? <Link to={s.path}>{content}</Link>
                      : <span aria-current={state === 'current' ? 'step' : undefined}>{content}</span>}
                  </li>
                )
              })}
            </ol>
          </nav>
          {/* 어느 단계에서든 새 광고로: 끝나지 않은 작업이면 확인을 받고, AI 요청 중에는 막는다 */}
          <button type="button" className="button secondary small new-ad" disabled={busy}
            onClick={() => { if (startNewAd()) navigate('/create/product') }}>
            새 광고
          </button>
        </div>
        <div className="stepper-bar" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s.path} className={i <= current ? 'on' : undefined} />)}
        </div>
      </header>
      {mock && (
        <div className="mock-bar" role="status">
          <div className="container mock-bar-inner">
            <span><strong>mock 모드</strong> · 서빙 서버·AI 없이 예시 데이터로 동작합니다. 결과는 실제 생성물이 아닙니다.</span>
            {import.meta.env.DEV && (
              <button type="button" className="button secondary small" onClick={() => setMock(false)}>실서버로 전환</button>
            )}
          </div>
        </div>
      )}
      <main id="create-main" className="create-main">
        <Outlet />
      </main>
    </div>
  )
}
