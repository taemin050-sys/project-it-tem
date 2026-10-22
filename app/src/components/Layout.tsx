import { NavLink, Outlet } from 'react-router-dom'

const STEPS = [
  { path: '/', label: '홈' },
  { path: '/product', label: '제품 정보' },
  { path: '/settings', label: '광고 설정' },
  { path: '/copy', label: '기획·카피' },
  { path: '/draft', label: '이미지 시안' },
  { path: '/export', label: '검증·내보내기' },
]

export default function Layout() {
  return (
    <div className="layout">
      <header className="header">
        <strong>광고 만들기</strong>
        <nav aria-label="작업 단계">
          <ol className="steps">
            {STEPS.map((s, i) => (
              <li key={s.path}>
                <NavLink to={s.path} end>
                  <span className="step-num">{i + 1}</span>
                  {s.label}
                </NavLink>
              </li>
            ))}
          </ol>
        </nav>
      </header>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
