import { Link, Outlet, useLocation } from 'react-router-dom'
import { SERVICE_NAME } from '../config'
import { STEPS, stepIndex } from '../steps'

const STATE_TEXT = { done: '완료', current: '현재 단계', todo: '진행 전' } as const

// 지나온 단계만 되돌아갈 수 있고, 다음 단계는 각 화면의 버튼으로만 넘어간다
export default function CreateLayout() {
  const { pathname } = useLocation()
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
        </div>
        <div className="stepper-bar" aria-hidden="true">
          {STEPS.map((s, i) => <span key={s.path} className={i <= current ? 'on' : undefined} />)}
        </div>
      </header>
      <main id="create-main" className="create-main">
        <Outlet />
      </main>
    </div>
  )
}
