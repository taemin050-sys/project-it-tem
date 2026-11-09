import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { startNewAd } from '../api/useJob'
import { SERVICE_NAME } from '../config'
import { STEPS, stepIndex } from '../steps'
import { useProjectStore } from '../store/projectStore'
import Icon from './Icon'

const SIDE_STEPS = [
  { icon: 'inventory_2', label: '1단계 : 제품 정보 입력' },
  { icon: 'edit_note', label: '2단계 : 기획·카피 검토' },
  { icon: 'imagesmode', label: '3단계 : 인스타 비주얼 검토' },
  { icon: 'rocket_launch', label: '4단계 : 최종 소재 배포' },
]

// 시안 대시보드 틀: 왼쪽 사이드바(단계·팀 평가) + 위쪽 상단바. 지나온 단계만 되돌아갈 수 있다
export default function CreateLayout() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const busy = useProjectStore((s) => s.run.busy)
  const mock = useProjectStore((s) => s.mock)
  const setMock = useProjectStore((s) => s.setMock)
  const current = stepIndex(pathname)
  // 어느 단계에서든 새 광고로: 끝나지 않은 작업이면 확인을 받고, AI 요청 중에는 막는다
  const newAd = () => { if (startNewAd()) navigate('/create/product') }

  return (
    <div className="create">
      <a className="skip-link" href="#create-main">본문 바로가기</a>
      <div className="rainbow-bar" aria-hidden="true" />
      <div className="studio">
        <aside className="side" aria-label="광고 만들기 메뉴">
          <Link to="/" className="side-logo" aria-label={`${SERVICE_NAME} 홈`}>
            <strong>{SERVICE_NAME}</strong>
            <span>Studio Workflow</span>
          </Link>
          <div className="side-progress">
            <div className="side-progress-row"><span>생성 워크플로우 진행도</span><b>{STEPS.length} Steps</b></div>
            <div className="side-progress-track"><span style={{ width: `${((current + 1) / STEPS.length) * 100}%` }} /></div>
          </div>
          <p className="side-label">생성 파이프라인</p>
          <ul className="side-nav">
            {SIDE_STEPS.map((s, i) => {
              const content = <><Icon name={s.icon} />{s.label}</>
              return (
                <li key={s.label}>
                  {i < current
                    ? <Link to={STEPS[i].path}>{content}</Link>
                    : <span className={i === current ? 'side-item is-current' : 'side-item is-todo'} aria-current={i === current ? 'step' : undefined}>{content}</span>}
                </li>
              )
            })}
          </ul>
          <p className="side-label gap">검수 및 거버넌스</p>
          <ul className="side-nav">
            <li><Link to="/team/evaluations"><Icon name="rate_review" />팀 공동 품질 평가</Link></li>
          </ul>
        </aside>

        <div className="studio-main">
          <header className="topbar">
            <div className="topbar-meta">
              <Link to="/" className="topbar-logo">{SERVICE_NAME}</Link>
              <span className="label-md text-variant hide-sm">K-Beauty AI Ad Studio</span>
              <span className="dot hide-sm" aria-hidden="true" />
              <span className="label-sm text-primary">실시간 식약처 규정 검사 활성</span>
            </div>
            <button type="button" className="button small" disabled={busy} onClick={newAd}>
              <Icon name="add" className="label-lg" />신규 소재 제작
            </button>
          </header>
          {mock && (
            <div className="mock-bar" role="status">
              <div className="mock-bar-inner">
                <span><strong>mock 모드:</strong> 서버와 AI 없이 예시 데이터로 동작합니다. 실제 생성 결과가 아닙니다.</span>
                {import.meta.env.DEV && (
                  <button type="button" className="button secondary small" onClick={() => setMock(false)}>실서버로 전환</button>
                )}
              </div>
            </div>
          )}
          <main id="create-main" className="studio-content">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  )
}
