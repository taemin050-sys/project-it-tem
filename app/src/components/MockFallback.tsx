import { useProjectStore } from '../store/projectStore'

// 서버에 닿지 못했을 때만 보여주는 개발용 전환. 누르기 전에는 mock으로 바꾸지 않는다 (FRONTEND.md 3장: 조용한 mock 전환 금지)
export default function MockFallback({ onSwitch }: { onSwitch?: () => void }) {
  const setMock = useProjectStore((s) => s.setMock)
  const mock = useProjectStore((s) => s.mock)
  if (!import.meta.env.DEV || mock) return null
  return (
    <p className="field-hint">
      서빙 서버 없이 화면만 확인하려면{' '}
      <button type="button" className="button secondary small" onClick={() => { setMock(true); onSwitch?.() }}>
        mock으로 테스트하기
      </button>
    </p>
  )
}
