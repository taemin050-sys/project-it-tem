import type { ReactNode } from 'react'

type Props = {
  /** 페이지 위 전체 폭 띠 (1단계 시안의 단계 알약) */
  top?: ReactNode
  children: ReactNode
  /** 하단 작업 영역 왼쪽: 확인 체크·상태·오류 문구 */
  note?: ReactNode
  /** 하단 작업 영역 오른쪽: 이전·다음 버튼 */
  actions?: ReactNode
  /** sticky: 화면 아래에 붙는 카드(2단계), card: 흐름 안의 카드(3단계), plain: 배경 없는 줄(1·4단계) */
  bar?: 'sticky' | 'card' | 'plain'
}

// 모든 단계가 같은 페이지 폭과 하단 작업 영역 위치를 쓰도록 하는 틀
export default function StepPage({ top, children, note, actions, bar = 'sticky' }: Props) {
  return (
    <>
      {top}
      <div className="page">
        <div className="page-glow" aria-hidden="true" />
        {children}
        {(note || actions) && (
          <div className={bar === 'card' ? 'action-bar' : `action-bar ${bar}`}>
            {note && <div className="action-note">{note}</div>}
            {actions}
          </div>
        )}
      </div>
    </>
  )
}
